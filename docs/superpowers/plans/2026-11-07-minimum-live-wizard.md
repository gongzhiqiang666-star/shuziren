# Minimum Live Validation Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent five-step validation wizard that checks, guides, and records a minimum real live chain without controlling any external process.

**Architecture:** PostgreSQL stores shop-scoped runs and gate evidence behind authenticated Go APIs with optimistic locking. A Vue view presents fixed commands, validates evidence, and exports a redacted JSON record. No endpoint accepts commands, credentials, media uploads, or process-control requests.

**Tech Stack:** Go 1.27/Gin/pgx/PostgreSQL, Vue 3/TypeScript/Vitest, existing browser harness.

---

### Task 1: Domain contract and migration

**Files:**
- Create: `server/internal/domain/live_readiness.go`
- Create: `server/internal/domain/live_readiness_test.go`
- Create: `server/internal/store/migrations/008_live_readiness.sql`

- [ ] Write failing domain tests for five default blocked gates, evidence rules, sensitive-key/path rejection, and four conclusions.
- [ ] Run `cd server && go test ./internal/domain -run LiveReadiness -count=1`; expect failure because types are missing.
- [ ] Implement `LiveReadinessRun`, `LiveReadinessGate`, `LiveReadinessEvidence`, constants, `ValidateLiveReadinessGate`, and `LiveReadinessConclusion`.
- [ ] Add tables `live_readiness_runs` and `live_readiness_gates` with shop foreign key, fixed gate/status checks, JSONB evidence, version, and timestamps.
- [ ] Re-run the focused test; expect PASS.
- [ ] Commit: `feat: define live readiness records`.

Evidence rules implemented in the test must be exact:

```go
generation := domain.LiveReadinessGate{Name: "generation", Status: "passed", Evidence: map[string]any{"new_text": true, "wav_sha256": strings.Repeat("a", 64), "listened": true, "same_wav": true}}
obs := domain.LiveReadinessGate{Name: "obs", Status: "passed", Evidence: map[string]any{"output_mode": "virtual_camera", "video": "recording-01", "audio": "recording-01", "reviewed": true}}
```

### Task 2: Store and API

**Files:**
- Create: `server/internal/store/live_readiness.go`
- Create: `server/internal/api/live_readiness.go`
- Create: `server/internal/api/live_readiness_test.go`
- Modify: `server/internal/api/extensions.go`

- [ ] Write failing authenticated API tests for create/list/get/update/export, shop isolation, stale version, invalid passed evidence, sensitive evidence, and platform blocked conclusion.
- [ ] Run `cd server && go test ./internal/api -run LiveReadiness -count=1`; expect route failures.
- [ ] Implement transactional store functions that create all five gates, lock the run on update, verify shop ownership/version, update one gate, recalculate conclusion, and return stable ordered gates.
- [ ] Register only the five record APIs from the approved design. Do not add execute/start/stop/install/upload routes.
- [ ] Export a stable object containing run metadata, gate status/evidence/note, and conclusion only.
- [ ] Re-run focused API tests; expect PASS.
- [ ] Commit: `feat: add live readiness record API`.

### Task 3: Frontend types and validation

**Files:**
- Create: `web/src/readiness/types.ts`
- Create: `web/src/readiness/validation.ts`
- Create: `web/src/readiness/validation.test.ts`

- [ ] Write failing Vitest cases for required generation/OBS/platform evidence, blocked platform, conclusion labels, and secret/path rejection.
- [ ] Run `cd web && npm test -- src/readiness/validation.test.ts`; expect missing module failure.
- [ ] Implement pure validators matching the Go contract and fixed command constants. No command may be user-editable.
- [ ] Re-run focused tests; expect PASS.
- [ ] Commit: `feat: validate live readiness evidence in web`.

### Task 4: Five-step wizard view

**Files:**
- Create: `web/src/readiness/LiveReadinessView.vue`
- Create: `web/src/readiness/LiveReadinessView.test.ts`
- Modify: `web/src/App.vue`
- Modify: `web/src/style.css`

- [ ] Write failing component tests for navigation, creating/resuming a run, fixed preflight command, saving install/generation/OBS, platform blocked display, export, and absence of process-control requests.
- [ ] Run `cd web && npm test -- src/readiness/LiveReadinessView.test.ts`; expect missing component failure.
- [ ] Implement the wizard with step cards, explicit external-action instructions, per-field errors, save feedback, run history selector, and JSON download.
- [ ] Add `readiness` to the `Page` union and sidebar as “开播验证”; render it before the QualityView fallback.
- [ ] Add responsive styles without changing existing page behavior.
- [ ] Re-run focused component tests and `npm run build`; expect PASS.
- [ ] Commit: `feat: add minimum live validation wizard`.

### Task 5: Browser acceptance and documentation

**Files:**
- Modify: `tests/browser/business.cjs`
- Modify: `docs/MINIMUM_LIVE_RUNBOOK.md`
- Modify: `docs/IMPLEMENTATION_STATUS.md`

- [ ] Add browser flow: open “开播验证”, create run, record install/generation/OBS, leave platform blocked, verify `local_chain_passed_platform_blocked`, download/export through API, and confirm no process-control network calls.
- [ ] Update the runbook with page-first instructions and retain PowerShell as the external preflight source.
- [ ] Record that the wizard is implemented but Windows/NVIDIA/OBS evidence remains pending.
- [ ] Run browser acceptance using the established project command when PostgreSQL/browser dependencies are available; otherwise run all unit/build checks and explicitly preserve browser validation as unverified.
- [ ] Commit: `test: cover minimum live wizard flow`.

### Task 6: Completion audit

**Files:**
- Modify only if verification exposes defects.

- [ ] Run `cd server && go test ./...` and `go vet ./...`.
- [ ] Run `cd web && npm test` and `npm run build`.
- [ ] Run `make test-live-readiness`.
- [ ] Run `git diff --check` and inspect `git status --short`.
- [ ] Search production code for readiness routes containing execute/start/stop/install/upload and confirm none exist.
- [ ] Confirm the UI only checks, guides, records, and exports; external processes remain operator-started.
- [ ] Commit verification fixes if required; do not create an empty commit.
