# yunchuang_v122 One-Click Proof Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a safe offline toolkit whose local webpage lets a non-developer record or select authorized person and voice material, create the first v122 avatar on an empty RTX 3060 Windows computer, generate fresh speech, drive the avatar with that exact WAV, and immediately review an MP4 and evidence report.

**Architecture:** Keep redistributable orchestration code in this repository and keep the commercial runtime, weights, inputs, and outputs in an ignored transfer directory. A loopback-only Python service serves a dependency-free recording wizard and owns uploads, validation, run state, subprocess ownership, evidence, and reports; thin CMD/PowerShell entry points start or diagnose it. The v122 adapter is evidence-driven: discovery first records the real executable/module entry points, then the adapter invokes only confirmed commands without embedding proprietary code.

**Tech Stack:** Python 3.11 standard library, PowerShell 5.1+, Windows CMD, ffmpeg/ffprobe, NVIDIA CLI, unittest, HTML5 audio/video.

---

## File map

- `scripts/v122_proof.py`: portable CLI, config validation, material probing, run lifecycle, freshness/same-WAV checks, report generation.
- `scripts/v122_proof_server.py`: loopback HTTP API, bounded media upload, run state, stage retry, and current-run deletion.
- `scripts/v122_adapter.py`: confirmed v122 command construction and output contracts; no proprietary implementation.
- `scripts/build_v122_proof.py`: safe Mac-side offline package builder and SHA-256 manifest writer.
- `scripts/v122-proof/windows/`: fixed CMD menu and PowerShell hardware/process helpers copied into the package.
- `scripts/v122-proof/web/index.html`: four-step recording and generation wizard.
- `scripts/v122-proof/web/app.js`: camera/microphone MediaRecorder state machine and API client.
- `scripts/v122-proof/web/style.css`: responsive local operator UI.
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

### Task 3: Build the loopback-only enrollment API

**Files:**
- Create: `scripts/v122_proof_server.py`
- Modify: `scripts/test_v122_proof.py`

- [ ] **Step 1: Write failing server contract tests**

Start the server on an ephemeral port and assert: it binds `127.0.0.1`; `GET /api/state` creates or resumes one current run; `POST /api/materials/person` and `/api/materials/voice` accept bounded media bodies; `PUT /api/text` accepts only `reference_transcript` and `new_script`; `POST /api/materials/<kind>/confirm` records preview confirmation; `POST /api/generate` refuses incomplete inputs; `POST /api/stages/<stage>/retry` only retries a failed/blocked stage; `DELETE /api/current-run` requires `{"confirm":true}` and cannot escape the runs root.

- [ ] **Step 2: Confirm failure**

Run: `python3 -m unittest scripts.test_v122_proof.ServerTests -v`

Expected: FAIL because the loopback service is missing.

- [ ] **Step 3: Implement the fixed local API**

Use `ThreadingHTTPServer` with an explicit `("127.0.0.1", port)` bind, fixed routes, JSON response envelopes, `Content-Length` limits, extension/MIME allowlists, generated server-side filenames, atomic state writes, and `Cache-Control: no-store`. Reject proxy-style absolute URLs, encoded traversal, unexpected fields, and requests whose `Origin` is not the service origin.

- [ ] **Step 4: Implement persistent enrollment state**

Persist only the active run ID, relative material paths, SHA-256 values, preview confirmations, text fields, and stage statuses. On refresh, return enough state to restore previews and progress without exposing arbitrary filesystem paths.

- [ ] **Step 5: Run and commit**

Run: `python3 -m unittest scripts.test_v122_proof.ServerTests -v`

Expected: PASS.

Commit: `feat: add local v122 enrollment API`

### Task 4: Build the browser camera and microphone wizard

**Files:**
- Create: `scripts/v122-proof/web/index.html`
- Create: `scripts/v122-proof/web/app.js`
- Create: `scripts/v122-proof/web/style.css`
- Modify: `scripts/test_v122_proof.py`

- [ ] **Step 1: Write failing static UI contract tests**

Require four visible steps, buttons `开始摄像头录制`, `选择已有视频`, `开始麦克风录音`, `选择已有WAV`, `检查并开始生成`, and `删除本次素材`; require video preview, audio preview, transcript and new-script fields, stage list, generated-WAV player, final-MP4 player, and confirmation dialog. Assert there are no CDN, remote URL, analytics, WebSocket, or arbitrary-command inputs.

- [ ] **Step 2: Confirm failure**

Run: `python3 -m unittest scripts.test_v122_proof.WebWizardTests -v`

Expected: FAIL because the wizard assets are missing.

- [ ] **Step 3: Implement person recording state**

Use `navigator.mediaDevices.getUserMedia({video:true,audio:false})`, a three-second countdown, `MediaRecorder`, elapsed-time display, stop at 60 seconds, preview via object URL, explicit `重录` and `确认人物视频`, and file-input fallback. Do not request microphone permission during person recording.

- [ ] **Step 4: Implement voice recording state**

Use `getUserMedia({audio:{echoCancellation:false,noiseSuppression:false,autoGainControl:false},video:false})`, `AudioContext` analyser for a local level meter, stop at 30 seconds, audio preview, explicit `重录` and `确认参考声音`, and WAV/audio file fallback. Stop every media track after recording or cancellation.

- [ ] **Step 5: Implement text, progress, retry, and deletion flows**

Enable generation only after both media previews are confirmed and both text fields are non-empty. Poll `GET /api/state` while stages run; show `pending/running/passed/failed/blocked`, fixed error code, and retry only on failed/blocked stages. Require a second click in a modal before calling `DELETE /api/current-run`.

- [ ] **Step 6: Add browser-state tests without real devices**

Extract recorder state transitions into pure functions exposed under `window.__v122Test`; test idle → countdown → recording → preview → confirmed, permission denial → file fallback, refresh restore, and delete reset using a dependency-free DOM harness.

- [ ] **Step 7: Run and commit**

Run: `python3 -m unittest scripts.test_v122_proof.WebWizardTests -v`

Expected: PASS.

Commit: `feat: add browser person and voice enrollment`

### Task 5: Normalize browser recordings and validate all inputs

**Files:**
- Modify: `scripts/v122_proof.py`
- Modify: `scripts/v122_proof_server.py`
- Modify: `scripts/test_v122_proof.py`

- [ ] **Step 1: Write failing normalization tests**

With a fake ffmpeg/ffprobe runner, prove that uploaded or recorded person media becomes a fixed v122-compatible MP4 and voice media becomes mono 16-bit PCM WAV; originals remain under the run directory; conversion failure returns `MAT_CONVERT_VIDEO` or `MAT_CONVERT_AUDIO`; normalized outputs are probed again before confirmation.

- [ ] **Step 2: Confirm failure**

Run: `python3 -m unittest scripts.test_v122_proof.NormalizationTests -v`

Expected: FAIL because normalization is missing.

- [ ] **Step 3: Implement argument-array FFmpeg conversion**

Never invoke a shell. Convert video with fixed codec/frame/pixel-format arguments derived from the audited v122 contract and voice to mono PCM WAV at the required sample rate. Write to a temporary filename, probe it, then atomically promote it to the normalized material path.

- [ ] **Step 4: Implement material validation**

Cover video duration 20–60 seconds, one video stream, minimum 720p, supported frame rate, and readable frames; cover WAV duration 10–15.5 seconds and non-empty PCM samples; reject empty transcript/new script and append a cryptographically random run marker to the new script. Return fixed errors prefixed `MAT_VIDEO_`, `MAT_AUDIO_`, or `MAT_TEXT_`; do not claim to determine authorization, face suitability, or transcript accuracy.

- [ ] **Step 5: Run and commit**

Run: `python3 -m unittest scripts.test_v122_proof.NormalizationTests -v`

Expected: PASS.

Commit: `feat: normalize and validate recorded proof media`

### Task 6: Build and verify the offline transfer package

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

### Task 7: Validate selected files, transcript, and new script before GPU work

**Files:**
- Modify: `scripts/v122_proof.py`
- Modify: `scripts/test_v122_proof.py`

- [ ] **Step 1: Write failing material tests**

Mock `ffprobe` JSON and cover video duration 20–60 seconds, one video stream, minimum 720p, supported frame rate, and readable frames; cover WAV duration 10–15.5 seconds, mono/stereo PCM, no empty file; reject empty transcript/new script and append a cryptographically random run marker to the new script.

- [ ] **Step 2: Confirm failure**

Run: `python3 -m unittest scripts.test_v122_proof.MaterialTests -v`

Expected: FAIL because probing and validation are missing.

- [ ] **Step 3: Implement probing and machine-readable errors**

Implement `probe_video`, `probe_wav`, `validate_materials`, and `marked_script`. Return fixed error codes prefixed `MAT_VIDEO_`, `MAT_AUDIO_`, or `MAT_TEXT_`; do not pretend to determine authorization, face suitability, or transcript accuracy.

- [ ] **Step 4: Run and commit**

Run: `python3 -m unittest scripts.test_v122_proof.MaterialTests -v`

Expected: PASS.

Commit: `feat: validate v122 proof materials`

### Task 8: Add Windows startup, environment preflight, and safe process ownership

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

The primary launcher starts the loopback service, waits for `/api/state`, and opens the local wizard; the menu invokes only fixed Python subcommands for maintenance. `preflight.ps1` emits UTF-8 JSON with `pass`, `warning`, `blocked`, or `pending`; missing preprocessed character is `pending`. The stop helper terminates a process only when PID, executable path, creation time, and run ID match the owned-process registry.

- [ ] **Step 4: Parse PowerShell when available and run tests**

Run: `pwsh -NoProfile -Command '$e=$null; Get-ChildItem scripts/v122-proof/windows/*.ps1 | ForEach-Object { [System.Management.Automation.Language.Parser]::ParseFile($_.FullName,[ref]$null,[ref]$e)>$null }; if($e.Count){$e;exit 1}'`

Run: `python3 -m unittest scripts.test_v122_proof.WindowsContractTests -v`

Expected: PASS; if `pwsh` is absent on Mac, record parser check as pending for Windows rather than claiming it passed.

- [ ] **Step 5: Commit**

Commit: `feat: add safe Windows v122 proof launcher`

### Task 9: Orchestrate avatar creation, fresh TTS, same-WAV drive, and MP4 output

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

### Task 10: Generate and display a self-contained visual result

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

Use only local relative media links and HTML-escape all text. Write `reports/<run-id>/index.html`, copy it to `reports/latest/index.html`, and update the wizard so generated WAV and MP4 controls use fixed same-origin media routes without turning playback failures into inference success.

- [ ] **Step 4: Run and commit**

Run: `python3 -m unittest scripts.test_v122_proof.ReportTests -v`

Expected: PASS.

Commit: `feat: render v122 proof result page`

### Task 11: Document operator preparation and first-stage boundary

**Files:**
- Create: `docs/V122_PROOF_RUNBOOK.md`
- Modify: `docs/FUNCTION_MATRIX.md`
- Modify: `docs/MINIMUM_LIVE_RUNBOOK.md`
- Modify: `scripts/test_v122_proof.py`

- [ ] **Step 1: Write a failing runbook contract test**

Require a four-item preparation checklist, consent/authorization reminder, camera/microphone recording path, file-selection fallback, recommended video and WAV characteristics, exact package-build command, Windows copy and double-click flow, expected artifacts, staged failure codes, and explicit statements that first-stage acceptance ends at a reviewed local MP4 and Windows evidence is still pending.

- [ ] **Step 2: Confirm failure**

Run: `python3 -m unittest scripts.test_v122_proof.RunbookTests -v`

Expected: FAIL because the runbook is missing.

- [ ] **Step 3: Write the runbook and matrix links**

Make the first screen answer only: what four files/texts to prepare, where to copy them, what to double-click, and where the MP4 appears. Keep platform account/login outside the minimum proof.

- [ ] **Step 4: Run and commit**

Run: `python3 -m unittest scripts.test_v122_proof.RunbookTests -v`

Expected: PASS.

Commit: `docs: add v122 proof operator runbook`

### Task 12: Verify the redistributable toolkit on Mac without false completion claims

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

### Task 13: Execute the first RTX 3060 Windows proof

**Files:**
- Modify after evidence collection: `docs/FUNCTION_MATRIX.md`
- Store outside Git: `reports/<run-id>/`, `recordings/<run-id>.mp4`, `logs/<run-id>/`

- [ ] **Step 1: Prepare authorized inputs**

Use the webpage to record one 20–60 second front-facing person video and one 10–15 second clean reference recording, then provide its exact transcript and one new test script. If browser capture is unavailable, use the two file-selection fallbacks. Keep all four outside Git.

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

The implementation phase is complete when Tasks 1–12 pass and produce a verified offline package. The first-stage functional proof is complete only after Task 13 records or selects new person/voice material in the local webpage, creates a fresh WAV, and produces a playable same-WAV-driven MP4 on the RTX 3060 Windows computer. OBS belongs to the later live-output stage and cannot mask a failed local MP4.
