# yunchuang_v122 One-Click Proof Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a safe offline toolkit that lets a non-developer create the first v122 avatar from authorized video and voice material on an empty RTX 3060 Windows computer, generate fresh speech, drive the avatar with that exact WAV, and immediately review an MP4 and evidence report.

**Architecture:** Keep redistributable orchestration code in this repository and keep the commercial runtime, weights, inputs, and outputs in an ignored transfer directory. A Python CLI owns validation, run state, subprocess ownership, evidence, and reports; thin CMD/PowerShell entry points provide the Windows menu and hardware checks. The v122 adapter is evidence-driven: discovery first records the real executable/module entry points, then the adapter invokes only confirmed commands without embedding proprietary code.

**Tech Stack:** Python 3.11 standard library, PowerShell 5.1+, Windows CMD, ffmpeg/ffprobe, NVIDIA CLI, unittest, HTML5 audio/video.

---

## File map

- `scripts/v122_proof.py`: portable CLI, config validation, material probing, run lifecycle, freshness/same-WAV checks, report generation.
- `scripts/v122_adapter.py`: confirmed v122 command construction and output contracts; no proprietary implementation.
- `scripts/build_v122_proof.py`: safe Mac-side offline package builder and SHA-256 manifest writer.
- `scripts/v122-proof/windows/`: fixed CMD menu and PowerShell hardware/process helpers copied into the package.
- `scripts/v122-proof/web/report.html`: self-contained result template.
- `scripts/test_v122_proof.py`: portable unit and contract tests.
- `config/v122-proof.example.json`: secret-free schema example with relative package paths.
- `docs/evidence/v122-runtime-map.md`: runtime entry points and confidence/evidence; no binaries or recovered commercial source.
- `docs/V122_PROOF_RUNBOOK.md`: operator preparation, copy, run, review, and failure recovery.
- `docs/FUNCTION_MATRIX.md`: authoritative status rows for this minimum chain, created in Task 1.
- `.gitignore`: excludes runtime, materials, reports, recordings, logs, and generated transfer directories.

### Task 1: Audit the local v122 package and freeze the real invocation contract

**Files:**
- Create: `docs/evidence/v122-runtime-map.md`
- Create: `scripts/test_v122_proof.py`
- Create: `docs/FUNCTION_MATRIX.md`

- [ ] **Step 1: Add a failing evidence-contract test**

Add `EvidenceTests.test_runtime_map_names_every_required_stage`, requiring the map to contain `environment`, `avatar_preprocess`, `voice_generate`, `avatar_drive`, `mp4_output`, each with an entry point, inputs, outputs, and evidence path.

- [ ] **Step 2: Run the focused test and confirm failure**

Run: `python3 -m unittest scripts.test_v122_proof.EvidenceTests -v`

Expected: FAIL because `docs/evidence/v122-runtime-map.md` does not exist.

- [ ] **Step 3: Perform read-only runtime discovery**

Inspect `/Users/apple/claudelife/shuziren/yunchuang_v122` for launchers, configuration, logs, strings, recovered source, and module lists. Record exact relative paths and command shapes, but do not copy binaries, weights, credentials, user data, or proprietary source into Git. Mark each stage `confirmed`, `inferred`, or `unknown`; an unknown core entry point is a Windows probe requirement, not a guessed command.

- [ ] **Step 4: Update the feature matrix honestly**

Add rows for material validation, avatar preprocessing, voice generation, same-WAV avatar drive, MP4 mux, and OBS handoff. Initial state is `已分析` only where evidence supports the contract; all Windows/GPU states remain `未验证`.

- [ ] **Step 5: Run and commit**

Run: `python3 -m unittest scripts.test_v122_proof.EvidenceTests -v`

Expected: PASS.

Commit: `docs: map v122 minimum proof entry points`

### Task 2: Define safe proof configuration and input contracts

**Files:**
- Create: `config/v122-proof.example.json`
- Create: `scripts/v122_proof.py`
- Modify: `scripts/test_v122_proof.py`

- [ ] **Step 1: Write failing config tests**

Cover: unknown keys rejected; absolute paths and `..` rejected; secrets such as `token`, `cookie`, and `api_key` rejected; required inputs are `person_video`, `reference_wav`, `reference_transcript`, and `new_script`; RTX 3060 selects `env`, never `env_50`.

- [ ] **Step 2: Confirm failure**

Run: `python3 -m unittest scripts.test_v122_proof.ConfigTests -v`

Expected: FAIL because the config API is missing.

- [ ] **Step 3: Implement the minimal config API**

Implement `load_config(path)`, `validate_config(data)`, `resolve_package_path(root, relative)`, and `select_environment(gpu_name)`. Permit only paths under the package root and use a fixed command-stage schema populated from the audited runtime map.

- [ ] **Step 4: Add the secret-free example**

Use relative paths under `materials/`, `runtime/yunchuang_v122/`, `reports/`, and `recordings/`; use no real names, voices, machine paths, or credentials.

- [ ] **Step 5: Run and commit**

Run: `python3 -m unittest scripts.test_v122_proof.ConfigTests -v`

Expected: PASS.

Commit: `feat: define v122 proof configuration`

### Task 3: Build and verify the offline transfer package

**Files:**
- Create: `scripts/build_v122_proof.py`
- Modify: `scripts/test_v122_proof.py`
- Modify: `.gitignore`

- [ ] **Step 1: Write failing builder tests**

Use temporary directories to prove that the builder rejects a non-empty destination, source/destination overlap, symlinks, path escape, missing required runtime files, and changed files during copy. Assert the manifest contains sorted relative paths, byte sizes, and SHA-256 values.

- [ ] **Step 2: Confirm failure**

Run: `python3 -m unittest scripts.test_v122_proof.BuilderTests -v`

Expected: FAIL because the builder is missing.

- [ ] **Step 3: Implement a copy-only builder**

Require explicit `--runtime-source` and `--destination`; create only a new empty destination; copy the runtime plus tracked proof scripts; write `proof/manifests/package.json`; never delete or overwrite a destination and never follow links.

- [ ] **Step 4: Protect generated/private data**

Ignore `v122-minimum-proof/`, `materials/`, `runtime/`, `reports/`, `recordings/`, `logs/`, and local proof configs while retaining the example config.

- [ ] **Step 5: Run and commit**

Run: `python3 -m unittest scripts.test_v122_proof.BuilderTests -v`

Expected: PASS.

Commit: `feat: build safe v122 offline proof package`

### Task 4: Validate video, voice, transcript, and new script before GPU work

**Files:**
- Modify: `scripts/v122_proof.py`
- Modify: `scripts/test_v122_proof.py`

- [ ] **Step 1: Write failing material tests**

Mock `ffprobe` JSON and cover video duration 20–60 seconds, one video stream, minimum 720p, supported frame rate, and readable frames; cover WAV duration 10–30 seconds, mono/stereo PCM, no empty file; reject empty transcript/new script and append a cryptographically random run marker to the new script.

- [ ] **Step 2: Confirm failure**

Run: `python3 -m unittest scripts.test_v122_proof.MaterialTests -v`

Expected: FAIL because probing and validation are missing.

- [ ] **Step 3: Implement probing and machine-readable errors**

Implement `probe_video`, `probe_wav`, `validate_materials`, and `marked_script`. Return fixed error codes prefixed `MAT_VIDEO_`, `MAT_AUDIO_`, or `MAT_TEXT_`; do not pretend to determine authorization, face suitability, or transcript accuracy.

- [ ] **Step 4: Run and commit**

Run: `python3 -m unittest scripts.test_v122_proof.MaterialTests -v`

Expected: PASS.

Commit: `feat: validate v122 proof materials`

### Task 5: Add Windows menu, environment preflight, and safe process ownership

**Files:**
- Create: `scripts/v122-proof/windows/00_开始验证.cmd`
- Create: `scripts/v122-proof/windows/01_环境检查.cmd`
- Create: `scripts/v122-proof/windows/03_创建人物并生成录像.cmd`
- Create: `scripts/v122-proof/windows/04_打开OBS.cmd`
- Create: `scripts/v122-proof/windows/05_查看结果.cmd`
- Create: `scripts/v122-proof/windows/99_停止验证.cmd`
- Create: `scripts/v122-proof/windows/preflight.ps1`
- Create: `scripts/v122-proof/windows/stop-owned.ps1`
- Modify: `scripts/test_v122_proof.py`

- [ ] **Step 1: Write failing static Windows tests**

Assert the numbered menu has only fixed choices, uses quoted paths, contains no `Invoke-Expression`, no unrestricted prompt execution, no `taskkill /IM`, and no PowerShell policy or firewall changes. Require checks for Windows, disk, `nvidia-smi`, driver, VRAM, Torch CUDA, ONNX provider, ffmpeg/ffprobe, model inventory, OBS, virtual camera, SRS, and ports.

- [ ] **Step 2: Confirm failure**

Run: `python3 -m unittest scripts.test_v122_proof.WindowsContractTests -v`

Expected: FAIL because entry points are missing.

- [ ] **Step 3: Implement thin launchers and preflight**

The menu invokes only fixed Python subcommands. `preflight.ps1` emits UTF-8 JSON with `pass`, `warning`, `blocked`, or `pending`; missing preprocessed character is `pending`. The stop helper terminates a process only when PID, executable path, creation time, and run ID match the owned-process registry.

- [ ] **Step 4: Parse PowerShell when available and run tests**

Run: `pwsh -NoProfile -Command '$e=$null; Get-ChildItem scripts/v122-proof/windows/*.ps1 | ForEach-Object { [System.Management.Automation.Language.Parser]::ParseFile($_.FullName,[ref]$null,[ref]$e)>$null }; if($e.Count){$e;exit 1}'`

Run: `python3 -m unittest scripts.test_v122_proof.WindowsContractTests -v`

Expected: PASS; if `pwsh` is absent on Mac, record parser check as pending for Windows rather than claiming it passed.

- [ ] **Step 5: Commit**

Commit: `feat: add safe Windows v122 proof launcher`

### Task 6: Orchestrate avatar creation, fresh TTS, same-WAV drive, and MP4 output

**Files:**
- Create: `scripts/v122_adapter.py`
- Modify: `scripts/v122_proof.py`
- Modify: `scripts/test_v122_proof.py`

- [ ] **Step 1: Write failing adapter and orchestration tests**

Use fake child processes and temporary files to prove: stages execute in order; commands are argument arrays with no shell; non-zero exits stop the chain; each process is registered; TTS output must be created after run start and differ from prior hash; avatar drive receives that exact WAV path and SHA-256; MP4 must contain audio and video streams.

- [ ] **Step 2: Confirm failure**

Run: `python3 -m unittest scripts.test_v122_proof.OrchestrationTests -v`

Expected: FAIL because the adapter is missing.

- [ ] **Step 3: Implement only evidence-confirmed adapter calls**

Provide `build_preprocess_command`, `build_tts_command`, `build_drive_command`, and `build_mux_command` from the fixed configuration. If Task 1 left an entry point unknown, return `blocked` with code `V122_ENTRYPOINT_UNCONFIRMED`; do not guess or return success.

- [ ] **Step 4: Implement run state and metrics**

Create `reports/<run-id>/run.json`, `logs/`, `outputs/`, and `owned-processes.json`; capture stdout/stderr, stage duration, output hashes, first output time, frame count/FPS when observable, and periodic NVIDIA memory samples. Redact user home prefixes and secret-like fields.

- [ ] **Step 5: Run and commit**

Run: `python3 -m unittest scripts.test_v122_proof.OrchestrationTests -v`

Expected: PASS using fakes; matrix status remains static-only until Windows real execution.

Commit: `feat: orchestrate v122 minimum proof chain`

### Task 7: Generate and open a self-contained visual result

**Files:**
- Create: `scripts/v122-proof/web/report.html`
- Modify: `scripts/v122_proof.py`
- Modify: `scripts/test_v122_proof.py`

- [ ] **Step 1: Write failing report tests**

Assert the report contains environment/material/stage status, final marked text, WAV and MP4 controls, hashes, timings, FPS/VRAM evidence, OBS state, manual voice/person/lip ratings, error code and next action; assert it contains no token/cookie, raw environment dump, upstream response body, or absolute home path.

- [ ] **Step 2: Confirm failure**

Run: `python3 -m unittest scripts.test_v122_proof.ReportTests -v`

Expected: FAIL because report rendering is missing.

- [ ] **Step 3: Implement escaped report rendering**

Use only local relative media links and HTML-escape all text. Write `reports/<run-id>/index.html`, copy it to `reports/latest/index.html`, then open the WAV after TTS and the report after MP4 without turning media-open failures into inference success.

- [ ] **Step 4: Run and commit**

Run: `python3 -m unittest scripts.test_v122_proof.ReportTests -v`

Expected: PASS.

Commit: `feat: render v122 proof result page`

### Task 8: Document operator preparation and OBS handoff

**Files:**
- Create: `docs/V122_PROOF_RUNBOOK.md`
- Modify: `docs/FUNCTION_MATRIX.md`
- Modify: `docs/MINIMUM_LIVE_RUNBOOK.md`
- Modify: `scripts/test_v122_proof.py`

- [ ] **Step 1: Write a failing runbook contract test**

Require a four-item preparation checklist, consent/authorization reminder, recommended video and WAV characteristics, exact package-build command, Windows copy and double-click flow, menu choices, expected artifacts, staged failure codes, administrator-only virtual-camera step, OBS audio/video recording check, and explicit statement that Windows evidence is still pending.

- [ ] **Step 2: Confirm failure**

Run: `python3 -m unittest scripts.test_v122_proof.RunbookTests -v`

Expected: FAIL because the runbook is missing.

- [ ] **Step 3: Write the runbook and matrix links**

Make the first screen answer only: what four files/texts to prepare, where to copy them, what to double-click, and where the MP4 appears. Keep platform account/login outside the minimum proof.

- [ ] **Step 4: Run and commit**

Run: `python3 -m unittest scripts.test_v122_proof.RunbookTests -v`

Expected: PASS.

Commit: `docs: add v122 proof operator runbook`

### Task 9: Verify the redistributable toolkit on Mac without false completion claims

**Files:**
- Modify: `Makefile`
- Modify: `scripts/test_v122_proof.py`
- Modify: `docs/FUNCTION_MATRIX.md`

- [ ] **Step 1: Add aggregate commands**

Add `test-v122-proof` for all proof tests and `build-v122-proof` requiring explicit `V122_RUNTIME_SOURCE` and `V122_PROOF_DESTINATION` variables; fail when either is empty.

- [ ] **Step 2: Run the complete portable suite**

Run: `make test-v122-proof`

Expected: all config, builder, material, Windows-contract, orchestration, report, and runbook tests pass.

- [ ] **Step 3: Build into a new temporary destination**

Run: `V122_RUNTIME_SOURCE=/Users/apple/claudelife/shuziren/yunchuang_v122 V122_PROOF_DESTINATION=<new-empty-directory> make build-v122-proof`

Expected: manifest verification passes; no runtime/model/material/output file appears in `git status`.

- [ ] **Step 4: Audit repository boundaries**

Run: `git ls-files | rg '(pretrained_models|runtime/yunchuang|materials/|recordings/|reports/|\.pyd$|\.dll$|\.onnx$|\.pth$)'`

Expected: no prohibited payload files; documentation mentions are acceptable only when the match is a text file.

- [ ] **Step 5: Record accurate state and commit**

Mark portable toolkit rows `静态验证通过`; keep avatar creation, TTS, lip drive, MP4, virtual camera, and OBS at `待Windows验证`.

Commit: `test: verify v122 offline proof toolkit`

### Task 10: Execute the first RTX 3060 Windows proof

**Files:**
- Modify after evidence collection: `docs/FUNCTION_MATRIX.md`
- Store outside Git: `reports/<run-id>/`, `recordings/<run-id>.mp4`, `logs/<run-id>/`

- [ ] **Step 1: Prepare authorized inputs**

Provide one 20–60 second front-facing person video, one 10–30 second clean reference WAV, its exact transcript, and one new test script. Keep all four outside Git.

- [ ] **Step 2: Copy and verify the package**

Copy the generated directory to a short ASCII Windows path with at least 80GB free, run menu choice 1, and require package hashes, RTX 3060, driver, CUDA providers, ffmpeg, and models to pass before preprocessing.

- [ ] **Step 3: Run the single real chain**

Use menu choice 2 to validate inputs and choice 3 to create the person and generate the recording. Require a newly timestamped WAV, matching WAV hash in the drive stage, a playable MP4 with audio/video streams, and no swallowed stage error.

- [ ] **Step 4: Review the result before OBS**

Listen to the WAV and watch the local MP4. Record human ratings for identity, voice, lip sync, flicker, and audio/video synchronization. A failed qualitative rating is a failed proof even when processes exited zero.

- [ ] **Step 5: Verify OBS separately**

Only after MP4 passes, use the guided administrator step for virtual camera/SRS, open OBS, record 30 seconds, and confirm both picture and audio. Do not log into a live platform during this minimum proof.

- [ ] **Step 6: Update status from evidence**

Promote only demonstrated rows to `Windows验证通过` or `端到端验证通过`; retain failed/blocked rows with run ID, error code, and next experiment. Do not commit private reports, media, runtime files, or machine paths.

## Completion gate

The implementation phase is complete when Tasks 1–9 pass and produce a verified offline package. The minimum functional proof is complete only after Task 10 creates a fresh WAV and a playable same-WAV-driven MP4 from newly supplied person/voice material on the RTX 3060 Windows computer. OBS is a separate final gate and cannot mask a failed local MP4.
