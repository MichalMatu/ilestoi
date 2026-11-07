# IleStoi.pl — repository audit and repair candidate (2026-11-07)

Status: **OPEN — candidate, not accepted production**. This document records evidence, not a deployment approval.

## Verified entry snapshot

- Repository: `MichalMatu/ilestoi`; canonical released branch: `main`.
- Entry GitHub `main`: `83afe2ec0cba36a3facd497a9738cc3e4c57bbc6` (2026-11-04).
- Additional pre-existing branch: `fix/disable-automatic-actions-20261105` (one workflow-only commit ahead of entry `main`); not changed in this sprint.
- Recursive entry tree: **281 tracked files**, about **2.39 MB** total, not truncated. Main areas: Python HTTP (28), core (42), scripts (11), JS/HTML/CSS web (73), tests (78), migrations (7), deploy (9), docs (19).
- Commit history on `main` (committer dates, not per-file test evidence): **135** commits since 2026-10-31, **238** since 2026-10-08 and **238** since 2026-08-09. Recent changes include bounded multipart upload, SQL gallery batching, read-only readiness probes, and AI PDF/OpenAPI adapter. Earlier production/gallery acceptance is in the 2026-10-29 and 2026-11-01 checkpoints. Do not rerun those closed acceptance claims without regression evidence.
- Required operating model: `AGENTS.md`, `docs/TERMUX_DEVELOPMENT_FLOW.md`; production `main` is not a staging branch.

## Proven findings and scoped remediation

1. **Makefile shell recipe (reproduced):** `make help` had a missing continuation between `printf '%s\\n'` and its systemd arguments. A minimal Linux Sandbox reproduction exited **2** with `Syntax error: end of file unexpected (expecting "fi")`. Restoring the backslash made that reproduction exit **0**, printing the expected systemd instructions.
2. **Regression gap:** `tests/test_tooling_contracts.py` previously inspected Makefile strings without actually executing the systemd help path. Added a subprocess assertion on `make help SYSTEMD_MANAGED=1 RUNIT_MANAGED=0` and the instructions it must print.
3. **Health documentation drift:** code in `core/database.py::validate_readiness_database` performs a fast read-only schema/migration probe; `app/http/health.py` also checks writable root and disk reserve. It does **not** run photo-path validation, full SQLite quick_check or FK checks. Corrected `docs/START.md`, `docs/CURRENT_MODEL.md`, and `docs/DEPLOY.md` to keep these distinct from the full data diagnostic gate.
4. **Obsolete absolute development path:** examples pointing to `/home/test/Desktop/WreckScanner` did not describe the current isolated-worktree workflow. Replaced them with an explicit example isolated checkout in `README.md` and `docs/START.md` and linked the canonical Termux flow.
5. **Production deployment instructions:** `docs/DEPLOY.md` previously required a tag on `main` before candidate acceptance and prescribed the **mutating** `make e2e-report` command in the production post-deploy shell block. This contradicts `AGENTS.md`. Corrected to exact immutable candidate validation, post-acceptance `main`/tag promotion and read-only live smoke; the mutating E2E is explicitly restricted to an isolated test server/database. Strengthened `tests/test_docs_contracts.py` to reject the old tag prerequisite and a live E2E command.
6. Security/hardening reconnaissance included `app/http/request_body.py`, `rate_limit.py`, `proxy.py`, `auth.py`, `health.py`, `core/uploads.py`, `core/database.py`, `scripts/check.sh` and their matching unit contracts; no additional change was justified by a reproduced defect in that bounded review. **This is not a full security certification.**

No product feature or production database change was requested or made. The branch contains small commits for the above corrections only.

## Quality evidence and limitations

- **PASS (isolated Linux Sandbox, minimal reproduction):** original Makefile systemd snippet failed with shell exit 2; corrected snippet printed both systemd instructions and exited 0.
- **Not yet a full checkout result:** the ChatGPT Linux Sandbox has no DNS access to github.com, so a full clone/clean-environment gate could not be executed in that environment. The reproduction is deliberately distinguished from running the complete repository's `make help`.
- **Termux preflight task v1:** `ilestoi-general-audit-preflight-20261107-v1` rejected **before command execution** (invalid timeout finalization reserve). Preserve the failed receipt; never replay the ID.
- **Termux preflight task v2:** `ilestoi-general-audit-preflight-20261107-v2`; read its exact terminal result before making claims.
- **Candidate isolated QA task (earlier code snapshot):** `ilestoi-general-audit-candidate-qa-20261107-v1` targets candidate `bdf3b16d2aba6b25634f91aa0cdd350ffaa6bef3`. A later `tests/test_docs_contracts.py` update requires a fresh exact-SHA QA receipt for `cb7eacb252a7af2c2aa76d0907342dbcb6ba82a8` or its verified successor. It requests full Python unittest, focused regressions, Node test suite, Ruff lint/format, architecture diagnostics, offline npm install/lint, and read-only production health checks. Do not claim a PASS or skip failures without the result.
- **Native v1 QA terminal result (actual):** `ilestoi-general-audit-candidate-qa-20261107-v1` **FAILED before running any tests**: the selected live checkout was clean and its HEAD matched GitHub `main` at `83afe2ec0cba36a3facd497a9738cc3e4c57bbc6`, but the fetched review branch had already advanced to `548c6453880dac75e27b89bf18825318509ff41f` while that request pinned `bdf3b16d2aba6b25634f91aa0cdd350ffaa6bef3`. No worktree/test execution was reported. This is a strict stale-branch validation rejection, not a failing application test.
- **New exact-SHA native tasks:** focused docs/tooling `ilestoi-general-audit-candidate-docs-qa-20261107-v2`; full-suite `ilestoi-general-audit-candidate-full-qa-20261107-v3`, both on immutable code/test commit `cb7eacb252a7af2c2aa76d0907342dbcb6ba82a8`. Both check candidate ancestry after remote fetch, so later documentation-only branch commits cannot incorrectly invalidate the immutable source. Read results; no PASS is presumed.
- **Connector-side doc static assertions:** 6/6 checked true on the audit branch (no live mutating E2E command, post-deployment main/tag rule, legacy quickstart path removal, readiness distinction, handoff present). This is **not** a Python unittest execution.
- **Unverified pending:** full E2E/Chromium, exact clean sandbox clone, installation dependency security audit, production SQLite+photos integrity, active host/service status and release acceptance. No production deploy, tag or promotion is authorized by this candidate.
- The current `main` cannot be marked clean *on the phone* until live read-only preflight evidence is received. GitHub branch and source state are distinct from physical runtime state.

## Release and handoff

- Draft review: [PR #37](https://github.com/MichalMatu/ilestoi/pull/37) (never merge before guarded release acceptance).
- Work branch: `fix/audit-make-help-20261107`, based on `83afe2ec0cba36a3facd497a9738cc3e4c57bbc6`; candidate source tested by the queued QA task: `bdf3b16d2aba6b25634f91aa0cdd350ffaa6bef3`. Later documentation-only commits must be checked for diff/consistency, not silently relabeled as tested source.
- Exact Local Agent: host `android-termux-10520`, installation `6be16f1d-194b-4f07-b377-3d4bb218fcd7`, private repo `MichalMatu/local-agent`, branch `agent-control`.
- Read outputs in `.agent/hosts/android-termux-10520/supervisor/6be16f1d-194b-4f07-b377-3d4bb218fcd7/task-results/<task-id>.json`.
- Preserve the live `~/WreckScanner/WreckScanner`, database, photos, credentials, backups and current release. Development only in isolated `~/.local/state/ilestoi-dev/worktrees/`.
- On actual QA failure: reproduce, repair on same short-lived branch, add regression, request a new immutable exact-SHA QA task. On actual PASS: PR/review, verified predeployment SQLite snapshot and encrypted Restic, guarded production acceptance, only then fast-forward `main` and tag the exact deployed commit. Do not merge an unaccepted candidate into released `main`.
- [Continuation](../NEXT_CHAT.md). 
