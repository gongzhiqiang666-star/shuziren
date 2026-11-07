# Minimum yunchuang Live Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the smallest safe preparation kit needed to decide whether one real `yunchuang_v122`-style TTS → digital-human → OBS audio/video chain works on a Windows/NVIDIA machine.

**Architecture:** A platform-neutral Python command validates a declarative, secret-free asset manifest and creates evidence directories. A thin PowerShell wrapper collects Windows/NVIDIA/OBS/device facts and invokes the Python validator. A short runbook defines the five manual gates without claiming that diagnostics prove model quality or platform delivery.

**Tech Stack:** Python 3.11 standard library, PowerShell 5.1+, JSON, `unittest`, existing `scripts/doctor.py` safety conventions.

---

## File structure

- Create `config/live-readiness.example.json`: versioned, secret-free manifest schema and example paths.
- Create `scripts/live_readiness.py`: manifest validation, SHA-256 inventory, evidence-run initialization, and gate summary.
- Create `scripts/check-live-readiness.ps1`: Windows-only system, NVIDIA, OBS, audio-device, virtual-camera, SRS, and port diagnostics.
- Create `scripts/test_live_readiness.py`: unit tests for validation, redaction, hashing, run creation, and summary semantics.
- Create `docs/MINIMUM_LIVE_RUNBOOK.md`: shortest operator procedure from prerequisites through OBS proof.
- Modify `.gitignore`: keep local manifests and evidence outside Git while retaining the example manifest.
- Modify `Makefile`: add deterministic test and readiness commands.
- Modify `docs/FIRST_LIVE_VALIDATION.md`: point the existing milestone at the executable readiness kit.

### Task 1: Define and validate the secret-free manifest

**Files:**
- Create: `config/live-readiness.example.json`
- Create: `scripts/live_readiness.py`
- Create: `scripts/test_live_readiness.py`

- [ ] **Step 1: Write failing manifest tests**

Add tests that require schema `1`, reject unknown top-level keys, reject credential-like keys, require exactly one TTS engine and one avatar runtime, and allow an explicitly blocked platform gate:

```python
class ManifestTests(unittest.TestCase):
    def test_example_manifest_is_valid_and_secret_free(self):
        manifest = readiness.load_manifest(PROJECT / "config/live-readiness.example.json")
        readiness.validate_manifest(manifest)
        serialized = json.dumps(manifest).lower()
        for forbidden in ("password", "secret", "cookie", "session", "access_token"):
            self.assertNotIn(forbidden, serialized)

    def test_credentials_and_multiple_engines_are_rejected(self):
        manifest = readiness.example_manifest()
        manifest["credentials"] = {"cookie": "x"}
        with self.assertRaisesRegex(readiness.ReadinessError, "unknown key"):
            readiness.validate_manifest(manifest)
        manifest = readiness.example_manifest()
        manifest["tts"] = [{"name": "a"}, {"name": "b"}]
        with self.assertRaisesRegex(readiness.ReadinessError, "exactly one"):
            readiness.validate_manifest(manifest)
```

- [ ] **Step 2: Run the tests and verify failure**

Run:

```bash
python3 -m unittest scripts/test_live_readiness.py -v
```

Expected: import or attribute failure because `scripts/live_readiness.py` does not exist.

- [ ] **Step 3: Add the example manifest**

Use only path labels and public configuration; do not include keys, usernames, cookies, account IDs, or customer names:

```json
{
  "schema": 1,
  "runtime": {
    "root": "C:/yunchuang_v122/_internal",
    "environment": "env",
    "python": "env/python.exe"
  },
  "tts": {
    "name": "one-local-engine",
    "model_dir": "C:/live-assets/tts-model",
    "reference_audio": "C:/live-assets/voice/reference.wav",
    "reference_text": "C:/live-assets/voice/reference.txt"
  },
  "avatar": {
    "runtime": "yunchuang-image-infer",
    "model_dir": "C:/live-assets/avatar-model",
    "character_dir": "C:/live-assets/character-one"
  },
  "output": {
    "mode": "virtual_camera",
    "width": 1280,
    "height": 720,
    "fps": 25,
    "obs_scene": "minimum-live-proof"
  },
  "platform": {
    "required_for_this_run": false,
    "approval_status": "blocked"
  }
}
```

- [ ] **Step 4: Implement strict loading and validation**

Implement `ReadinessError`, `load_manifest(path)`, `example_manifest()`, and `validate_manifest(data)`. Validation must fail closed on unknown top-level keys, non-local absolute Windows paths, multiple engines, missing path fields, output dimensions outside 320–3840 × 240–2160, or FPS other than 25 for this first run. Walk every dictionary key and reject names matching:

```python
SENSITIVE_KEY = re.compile(
    r"(^|_)(password|passwd|secret|cookie|session|token|api_key|app_key|app_secret)($|_)",
    re.IGNORECASE,
)
```

The exception must name the field, never its value.

- [ ] **Step 5: Run the focused tests**

Run:

```bash
python3 -m unittest scripts/test_live_readiness.py -v
```

Expected: all manifest tests pass.

- [ ] **Step 6: Commit**

```bash
git add config/live-readiness.example.json scripts/live_readiness.py scripts/test_live_readiness.py
git commit -m "feat: define minimum live readiness manifest"
```

### Task 2: Add deterministic asset inventory and redacted reports

**Files:**
- Modify: `scripts/live_readiness.py`
- Modify: `scripts/test_live_readiness.py`

- [ ] **Step 1: Write failing inventory tests**

Create a temporary runtime with a fake DLL, model file, reference WAV, and character directory. Assert that the report contains only logical labels, presence, byte counts, and SHA-256 values—never the absolute temporary directory or file contents:

```python
def test_inventory_reports_hashes_without_paths_or_contents(self):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        model = root / "model.bin"
        model.write_bytes(b"private model fixture")
        report = readiness.inventory_paths({"tts.model_dir": model})
        serialized = json.dumps(report)
        self.assertEqual(report[0]["sha256"], hashlib.sha256(model.read_bytes()).hexdigest())
        self.assertNotIn(str(root), serialized)
        self.assertNotIn("private model fixture", serialized)
```

- [ ] **Step 2: Run the test and verify failure**

Run:

```bash
python3 -m unittest scripts.test_live_readiness.ManifestTests.test_inventory_reports_hashes_without_paths_or_contents -v
```

Expected: failure because `inventory_paths` is missing.

- [ ] **Step 3: Implement inventory collection**

Add `sha256_file`, `sha256_tree`, `manifest_paths`, and `inventory_paths`. Directory hashes must be stable: sort relative POSIX paths, hash each relative path plus file digest, ignore symlinks, and never traverse outside the declared directory. Reports use this shape:

```python
{
    "label": "tts.model_dir",
    "kind": "directory",
    "present": True,
    "bytes": 123456,
    "files": 42,
    "sha256": "64 lowercase hex characters"
}
```

Missing items have `present=false`, zero counts, and no fake digest.

- [ ] **Step 4: Add the `check-assets` CLI**

Support:

```bash
python3 scripts/live_readiness.py check-assets \
  --manifest config/live-readiness.local.json \
  --output test-results/live-readiness/assets.json
```

Exit `0` only when validation passes and every required local path exists; exit `2` for invalid manifests and `1` for missing assets. Print labels and statuses only.

- [ ] **Step 5: Run tests and a missing-assets smoke check**

Run:

```bash
python3 -m unittest scripts/test_live_readiness.py -v
python3 scripts/live_readiness.py check-assets --manifest config/live-readiness.example.json --output test-results/live-readiness/example-assets.json
```

Expected: tests pass; example command exits `1` on Mac because Windows example paths are intentionally absent, and its report contains no secrets.

- [ ] **Step 6: Commit**

```bash
git add scripts/live_readiness.py scripts/test_live_readiness.py
git commit -m "feat: inventory minimum live assets safely"
```

### Task 3: Create evidence runs and enforce gate semantics

**Files:**
- Modify: `scripts/live_readiness.py`
- Modify: `scripts/test_live_readiness.py`
- Modify: `.gitignore`

- [ ] **Step 1: Write failing run and summary tests**

Test that `init-run` creates one immutable metadata file and five gate files with `blocked` status. Test that an OBS gate cannot pass without both audio and video evidence, and that the platform gate may remain blocked without invalidating a local-only conclusion:

```python
def test_obs_gate_requires_audio_and_video_evidence(self):
    gate = {"status": "passed", "evidence": {"video": "obs-recording", "audio": ""}}
    with self.assertRaisesRegex(readiness.ReadinessError, "audio"):
        readiness.validate_gate("obs", gate)

def test_local_conclusion_stops_at_obs_when_platform_is_blocked(self):
    gates = readiness.empty_gates()
    for name in ("install", "generation", "obs"):
        gates[name] = {"status": "passed", "evidence": {"operator_record": name}}
    self.assertEqual(readiness.conclusion(gates), "local_chain_passed_platform_blocked")
```

- [ ] **Step 2: Run the tests and verify failure**

Run:

```bash
python3 -m unittest scripts/test_live_readiness.py -v
```

Expected: failures for missing run/gate helpers.

- [ ] **Step 3: Implement run creation and gate validation**

Add subcommands:

```bash
python3 scripts/live_readiness.py init-run --manifest config/live-readiness.local.json --root test-results/live-readiness
python3 scripts/live_readiness.py summarize --run test-results/live-readiness/20261107T120000Z
```

The run contains:

```text
metadata.json
assets.json
gates/install.json
gates/generation.json
gates/obs.json
gates/platform.json
gates/stability.json
summary.json
```

Allowed gate statuses are `passed`, `failed`, and `blocked`. `generation` requires a new-text record and WAV SHA-256; `obs` requires audio and video evidence; `platform` requires approval plus viewer evidence; `stability` is not required for the first local conclusion. Never inspect or copy media into Git-managed paths.

- [ ] **Step 4: Protect local state in `.gitignore`**

Add:

```gitignore
# Local minimum-live manifests and evidence
config/live-readiness.local.json
live-readiness-evidence/
```

Keep `config/live-readiness.example.json` tracked.

- [ ] **Step 5: Run all readiness tests**

Run:

```bash
python3 -m unittest scripts/test_live_readiness.py -v
```

Expected: all tests pass and no generated evidence is tracked.

- [ ] **Step 6: Commit**

```bash
git add .gitignore scripts/live_readiness.py scripts/test_live_readiness.py
git commit -m "feat: record minimum live validation gates"
```

### Task 4: Add the Windows/NVIDIA preflight wrapper

**Files:**
- Create: `scripts/check-live-readiness.ps1`
- Modify: `scripts/test_live_readiness.py`

- [ ] **Step 1: Write static safety tests for the PowerShell script**

Assert the script exists, accepts `-Manifest` and `-Output`, invokes `live_readiness.py check-assets`, uses `Get-CimInstance Win32_SoundDevice`, checks `nvidia-smi`, OBS, SRS, virtual-camera DLLs, and does not enumerate or print environment variables:

```python
def test_windows_preflight_has_required_checks_and_no_secret_dump(self):
    source = (PROJECT / "scripts/check-live-readiness.ps1").read_text(encoding="utf-8")
    for required in ("nvidia-smi", "Win32_SoundDevice", "obs64.exe", "srs-live.bat", "obs-virtualcam-module64.dll", "check-assets"):
        self.assertIn(required, source)
    for forbidden in ("Get-ChildItem Env:", "TAOBAO_APP_SECRET", "TAOBAO_SESSION", "APP_TOKEN"):
        self.assertNotIn(forbidden, source)
```

- [ ] **Step 2: Run the test and verify failure**

Run:

```bash
python3 -m unittest scripts.test_live_readiness.WindowsScriptTests -v
```

Expected: file-not-found failure.

- [ ] **Step 3: Implement the PowerShell wrapper**

The script must:

- use `[CmdletBinding()]` with required `-Manifest` and optional `-Output`;
- set `$ErrorActionPreference = 'Stop'`;
- resolve Python from the manifest and fall back to `py -3.11` only for the validator;
- collect Windows version, RAM, disk, GPU name/VRAM/driver, sound-device status, OBS executable presence, virtual-camera DLL presence, SRS script presence, WebView2 registry presence, and ports 8010/9880/1935;
- call the Python asset validator;
- emit one UTF-8 JSON report with `pass/fail/unverified` entries;
- exit nonzero when a required local prerequisite fails;
- never register DLLs, install drivers, start services, change registry state, or print credentials.

Use `Get-CimInstance` and `Get-NetTCPConnection` with caught errors; unavailable diagnostic APIs produce `unverified`, not false success.

- [ ] **Step 4: Parse-check PowerShell when available**

Run on Mac/Linux if `pwsh` exists:

```bash
pwsh -NoProfile -Command '$e=$null; [System.Management.Automation.Language.Parser]::ParseFile("scripts/check-live-readiness.ps1", [ref]$null, [ref]$e) > $null; if ($e.Count) { $e; exit 1 }'
```

Expected: exit `0`. If `pwsh` is absent, record this as not executed; the static Python tests must still pass. Repeat the same parser command on the target Windows machine before the first run.

- [ ] **Step 5: Run the readiness tests**

Run:

```bash
python3 -m unittest scripts/test_live_readiness.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/check-live-readiness.ps1 scripts/test_live_readiness.py
git commit -m "feat: add Windows live readiness preflight"
```

### Task 5: Write the shortest operator runbook

**Files:**
- Create: `docs/MINIMUM_LIVE_RUNBOOK.md`
- Modify: `docs/FIRST_LIVE_VALIDATION.md`
- Modify: `Makefile`

- [ ] **Step 1: Add documentation assertions**

Add a test that the runbook contains the fixed chain, stop conditions, Windows/NVIDIA requirement, local-only conclusion, five new sentences, same-WAV rule, OBS audio/video proof, and the exact preflight commands. Also assert it does not claim that HTTP success proves a live output.

- [ ] **Step 2: Run the documentation test and verify failure**

Run:

```bash
python3 -m unittest scripts.test_live_readiness.RunbookTests -v
```

Expected: file-not-found failure.

- [ ] **Step 3: Write `MINIMUM_LIVE_RUNBOOK.md`**

The runbook must fit this sequence:

1. Copy `config/live-readiness.example.json` to ignored `config/live-readiness.local.json` and edit paths only.
2. Run the PowerShell preflight and stop on required failures.
3. Initialize an evidence run.
4. Enter 5–10 previously unseen sentences; save exact text and WAV SHA-256.
5. Drive the single avatar runtime with the same WAV.
6. Capture the original-style virtual camera in OBS; if explicitly selected, use SRS as the single alternative output.
7. Record 10 minutes locally and confirm both audio and video before marking the OBS gate passed.
8. Stop the first milestone here when platform approval is unavailable.
9. When approval exists, verify the viewer side and update only the platform gate.
10. State that 30-minute and 8-hour stability are later gates, not requirements for deciding whether the first chain exists.

Include exact commands and a failure table for missing model, CUDA import failure, no TTS artifact, no virtual camera, picture-only OBS, audio-only OBS, and platform blocked.

- [ ] **Step 4: Wire commands into `Makefile`**

Add:

```make
.PHONY: test-live-readiness

test-live-readiness:
	python3 -m unittest scripts/test_live_readiness.py -v

check-live-readiness-example:
	python3 scripts/live_readiness.py check-assets --manifest config/live-readiness.example.json --output test-results/live-readiness/example-assets.json
```

The example check is expected to fail on non-Windows machines with absent example assets; it is not part of `make test`.

- [ ] **Step 5: Link the existing milestone document**

At the top of `docs/FIRST_LIVE_VALIDATION.md`, add a link to the new runbook and state that the runbook is the executable subset for the first OBS proof. Do not mark any existing acceptance box complete.

- [ ] **Step 6: Run tests and documentation checks**

Run:

```bash
make test-live-readiness
git diff --check
```

Expected: readiness tests pass and no whitespace errors.

- [ ] **Step 7: Commit**

```bash
git add docs/MINIMUM_LIVE_RUNBOOK.md docs/FIRST_LIVE_VALIDATION.md Makefile scripts/test_live_readiness.py
git commit -m "docs: add minimum live proof runbook"
```

### Task 6: Final preparation verification

**Files:**
- Modify only if verification exposes a defect in files from Tasks 1–5.

- [ ] **Step 1: Run the new focused suite**

```bash
make test-live-readiness
```

Expected: all readiness tests pass.

- [ ] **Step 2: Run the existing local-tool regression suite**

```bash
python3 -m pytest scripts/test_local_tools.py -q
```

Expected: all existing local-tool tests pass.

- [ ] **Step 3: Validate repository hygiene**

```bash
git diff --check
git status --short
git ls-files | rg '(live-readiness\.local\.json|live-readiness-evidence|test-results)'
```

Expected: no whitespace errors; status contains only intended changes or is clean after commits; the final command returns no tracked local evidence.

- [ ] **Step 4: Exercise safe failure on this Mac**

```bash
python3 scripts/live_readiness.py check-assets --manifest config/live-readiness.example.json --output test-results/live-readiness/mac-safe-failure.json
```

Expected: exit `1`, explicitly listing missing Windows paths by logical label without leaking absolute local paths or secrets. This is a successful preparation check, not a live-chain pass.

- [ ] **Step 5: Review completion boundaries**

Confirm the final handoff says:

- preparation kit complete;
- Windows/NVIDIA execution still pending;
- no model quality, OBS capture, or platform acceptance claimed;
- next action is one target-machine preflight, not more feature development.

- [ ] **Step 6: Commit verification fixes if needed**

If verification required changes:

```bash
git add config scripts docs Makefile .gitignore
git commit -m "test: verify minimum live readiness kit"
```

If no changes were required, do not create an empty commit.
