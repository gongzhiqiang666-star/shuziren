import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts.plugin_installer_manifest import audit_signatures, build, verify


class PluginInstallerManifestTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def installer(self, relative="MicrosoftEdgeWebview2Setup.exe", content=b"signed-installer-fixture"):
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return target

    def test_build_and_verify_approved_installers(self):
        self.installer()
        self.installer("VBCABLE_Driver_Pack45/VBCABLE_Setup_x64.exe", b"driver")
        manifest = build(self.root)
        self.assertEqual(manifest["version"], 1)
        self.assertEqual(set(manifest["files"]), {
            "MicrosoftEdgeWebview2Setup.exe",
            "VBCABLE_Driver_Pack45/VBCABLE_Setup_x64.exe",
        })
        self.assertEqual(verify(self.root), manifest)

    def test_tampering_is_rejected(self):
        installer = self.installer()
        build(self.root)
        installer.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "does not match"):
            verify(self.root)

    def test_unexpected_executable_is_rejected(self):
        self.installer()
        self.installer("unknown.exe")
        with self.assertRaisesRegex(ValueError, "unexpected executable"):
            build(self.root)

    @unittest.skipUnless(hasattr(os, "symlink"), "symbolic links unsupported")
    def test_linked_installer_is_rejected(self):
        external = self.root.parent / (self.root.name + "-external.exe")
        external.write_bytes(b"external")
        try:
            os.symlink(external, self.root / "MicrosoftEdgeWebview2Setup.exe")
        except OSError as error:
            self.skipTest(f"symbolic links unavailable: {error}")
        try:
            with self.assertRaisesRegex(ValueError, "escapes plugin root"):
                build(self.root)
        finally:
            external.unlink(missing_ok=True)

    def test_empty_directory_and_manifest_substitution_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "no approved"):
            build(self.root)
        self.installer()
        build(self.root)
        manifest_path = self.root / "installer-manifest.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["files"]["MicrosoftEdgeWebview2Setup.exe"]["size"] += 1
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "does not match"):
            verify(self.root)

    @patch("scripts.plugin_installer_manifest.sys.platform", "win32")
    def test_authenticode_audit_requires_valid_approved_publishers(self):
        self.installer()
        self.installer("VBCABLE_Driver_Pack45/VBCABLE_Setup_x64.exe", b"driver")
        runner = Mock(return_value=Mock(returncode=0, stdout=json.dumps([
            {"relative": "MicrosoftEdgeWebview2Setup.exe", "status": "Valid",
             "subject": "CN=Microsoft Corporation, O=Microsoft Corporation", "thumbprint": "A" * 40},
            {"relative": "VBCABLE_Driver_Pack45/VBCABLE_Setup_x64.exe", "status": "Valid",
             "subject": "CN=BUREL VINCENT Entrepreneur individuel", "thumbprint": "B" * 40},
        ])))
        result = audit_signatures(self.root, runner=runner)
        self.assertEqual(set(result), {
            "MicrosoftEdgeWebview2Setup.exe", "VBCABLE_Driver_Pack45/VBCABLE_Setup_x64.exe"})
        request = json.loads(runner.call_args.kwargs["input"])
        self.assertEqual([item["relative"] for item in request], list(result))

        runner.return_value.stdout = json.dumps([
            {"relative": "MicrosoftEdgeWebview2Setup.exe", "status": "NotSigned",
             "subject": None, "thumbprint": None},
            {"relative": "VBCABLE_Driver_Pack45/VBCABLE_Setup_x64.exe", "status": "Valid",
             "subject": "CN=BUREL VINCENT", "thumbprint": "B" * 40},
        ])
        with self.assertRaisesRegex(ValueError, "not valid"):
            audit_signatures(self.root, runner=runner)


if __name__ == "__main__":
    unittest.main()
