"""Build and verify the integrity manifest for approved bundled installers."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys


MANIFEST_NAME = "installer-manifest.json"
APPROVED_INSTALLERS = (
    "MicrosoftEdgeWebview2Setup.exe",
    "VBCABLE_Driver_Pack45/VBCABLE_Setup_x64.exe",
    "windowsdesktop-runtime-8.0.17-win-x64.exe",
    "windowsdesktop-runtime-9.0.6-win-x64.exe",
)
MAX_INSTALLER_SIZE = 1024 * 1024 * 1024
EXPECTED_SIGNERS = {
    "MicrosoftEdgeWebview2Setup.exe": "Microsoft Corporation",
    "windowsdesktop-runtime-8.0.17-win-x64.exe": "Microsoft Corporation",
    "windowsdesktop-runtime-9.0.6-win-x64.exe": "Microsoft Corporation",
    "VBCABLE_Driver_Pack45/VBCABLE_Setup_x64.exe": "BUREL VINCENT",
}


def _reparse(path):
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return path.is_symlink() or bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _digest(path):
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _approved_files(plugin_root):
    supplied_root = Path(plugin_root)
    if not supplied_root.is_dir() or _reparse(supplied_root):
        raise ValueError("plugin root must be a regular directory")
    root = supplied_root.resolve(strict=True)
    unexpected = []
    for candidate in root.rglob("*"):
        if candidate.is_file() and candidate.suffix.lower() == ".exe":
            relative = candidate.relative_to(root).as_posix()
            if relative not in APPROVED_INSTALLERS:
                unexpected.append(relative)
    if unexpected:
        raise ValueError("unexpected executable in plugin root: " + ", ".join(sorted(unexpected)))
    files = {}
    for relative in APPROVED_INSTALLERS:
        candidate = root / Path(relative)
        if not candidate.is_file():
            continue
        expected_parent = root / Path(relative).parent
        parents = [expected_parent]
        while parents[-1] != root:
            parents.append(parents[-1].parent)
        if (_reparse(candidate) or any(_reparse(parent) for parent in parents[:-1])
                or not candidate.resolve(strict=True).is_relative_to(root)):
            raise ValueError(f"installer escapes plugin root: {relative}")
        size = candidate.stat().st_size
        if size < 1 or size > MAX_INSTALLER_SIZE:
            raise ValueError(f"installer size is outside policy: {relative}")
        files[relative] = {"size": size, "sha256": _digest(candidate)}
    if not files:
        raise ValueError("no approved installers found")
    return root, files


def build(plugin_root):
    root, files = _approved_files(plugin_root)
    manifest = {"version": 1, "algorithm": "sha256", "files": files}
    destination = root / MANIFEST_NAME
    temporary = root / (MANIFEST_NAME + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as output:
            json.dump(manifest, output, ensure_ascii=False, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            import os
            os.fsync(output.fileno())
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return manifest


def verify(plugin_root):
    root, actual = _approved_files(plugin_root)
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.is_file() or _reparse(manifest_path):
        raise ValueError("installer manifest is missing or unsafe")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("installer manifest is unreadable") from error
    if not isinstance(manifest, dict) or manifest.get("version") != 1 or manifest.get("algorithm") != "sha256":
        raise ValueError("unsupported installer manifest")
    if manifest.get("files") != actual:
        raise ValueError("installer manifest does not match bundled files")
    return manifest


def audit_signatures(plugin_root, *, runner=subprocess.run):
    """Verify Windows Authenticode and expected publishers before manifest build."""
    if sys.platform != "win32":
        raise OSError("Authenticode audit requires Windows")
    root, files = _approved_files(plugin_root)
    requests = [{"relative": relative, "path": str(root / Path(relative))} for relative in files]
    script = r"""
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Import-Module (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\Modules\Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1') -Force
$requests = [Console]::In.ReadToEnd() | ConvertFrom-Json
$result = foreach ($item in $requests) {
  $signature = Get-AuthenticodeSignature -LiteralPath $item.path
  [pscustomobject]@{
    relative = $item.relative
    status = [string]$signature.Status
    subject = if ($signature.SignerCertificate) { $signature.SignerCertificate.Subject } else { $null }
    thumbprint = if ($signature.SignerCertificate) { $signature.SignerCertificate.Thumbprint } else { $null }
  }
}
@($result) | ConvertTo-Json -Depth 3 -Compress
"""
    environment = dict(os.environ)
    system_root = Path(environment.get("SystemRoot", r"C:\Windows"))
    environment["PSModulePath"] = os.pathsep.join((
        str(system_root / "System32/WindowsPowerShell/v1.0/Modules"),
        str(Path(environment.get("ProgramFiles", r"C:\Program Files")) / "WindowsPowerShell/Modules"),
    ))
    powershell = system_root / "System32/WindowsPowerShell/v1.0/powershell.exe"
    completed = runner(
        [str(powershell), "-NoProfile", "-NonInteractive", "-Command", script],
        input=json.dumps(requests), capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), env=environment,
    )
    if completed.returncode:
        detail = (completed.stderr or "").strip().splitlines()
        suffix = f": {detail[-1]}" if detail else ""
        raise ValueError("Authenticode audit failed to run" + suffix)
    try:
        records = json.loads(completed.stdout)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("Authenticode audit returned invalid output") from error
    if not isinstance(records, list) or len(records) != len(requests):
        raise ValueError("Authenticode audit returned an incomplete result")
    by_relative = {record.get("relative"): record for record in records if isinstance(record, dict)}
    result = {}
    for request in requests:
        relative = request["relative"]
        record = by_relative.get(relative)
        expected = EXPECTED_SIGNERS[relative]
        if not record or record.get("status") != "Valid":
            raise ValueError(f"installer Authenticode signature is not valid: {relative}")
        subject = str(record.get("subject") or "")
        if expected.casefold() not in subject.casefold():
            raise ValueError(f"installer publisher is not approved: {relative}")
        thumbprint = str(record.get("thumbprint") or "").strip().upper()
        if len(thumbprint) != 40 or any(character not in "0123456789ABCDEF" for character in thumbprint):
            raise ValueError(f"installer signer thumbprint is invalid: {relative}")
        result[relative] = {"status": "Valid", "subject": subject, "thumbprint": thumbprint}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("audit-signatures", "build", "verify"))
    parser.add_argument("--plugin-root", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "audit-signatures":
        signatures = audit_signatures(args.plugin_root)
        print(json.dumps({"verified": True, "files": len(signatures), "signatures": signatures}, ensure_ascii=False))
    else:
        manifest = build(args.plugin_root) if args.command == "build" else verify(args.plugin_root)
        print(json.dumps({"verified": True, "files": len(manifest["files"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
