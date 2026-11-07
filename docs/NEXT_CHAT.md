# IleStoi.pl — next session (2026-11-07 audit candidate)

## First action

Read `AGENTS.md`, `docs/TERMUX_DEVELOPMENT_FLOW.md` and `docs/checkpoints/2026-11-07-general-repository-audit-candidate.md`. Fetch **fresh** GitHub `main` and work-branch refs; never assume the SHA below remained unchanged. Do not rerun completed Oct/Nov release audits without fresh regression evidence.

- Repository: `MichalMatu/ilestoi`.
- Entry released `main`: `83afe2ec0cba36a3facd497a9738cc3e4c57bbc6`.
- Audit fix branch: `fix/audit-make-help-20261107`.
- Candidate source QA SHA: `bdf3b16d2aba6b25634f91aa0cdd350ffaa6bef3` (subsequent checkpoint/handoff documentation commits are docs-only, verify).
- Previous production installation and candidate QA are **not automatically accepted**. Read exact contemporary evidence.

## Targeted Local Agent

- Private transport repository: `MichalMatu/local-agent`, branch `agent-control`.
- Host: `android-termux-10520`; installation: `6be16f1d-194b-4f07-b377-3d4bb218fcd7`.
- Result directory:
  `.agent/hosts/android-termux-10520/supervisor/6be16f1d-194b-4f07-b377-3d4bb218fcd7/task-results/`.
- Preflight v1 `ilestoi-general-audit-preflight-20261107-v1` failed validation before execution (timeout reserve). Do **not** reuse this ID.
- Preflight v2 `ilestoi-general-audit-preflight-20261107-v2` requests live read-only Git/worktree, service, health and Makefile diagnostics.
- QA `ilestoi-general-audit-candidate-qa-20261107-v1` requests a disposable worktree on exact candidate SHA, focused/full Python unittest, JS tests, Ruff, architecture and offline lint, plus before/after production read-only checks.
- An immutable task file and Git publish do not count as execution; read **terminal** result JSON and command return code. If a task ends UNKNOWN, investigate without replay.
- Never redirect ordinary IleStoi Host Ops to Mac. Only explicitly unavailable browser tests may use Mac with selected host identity.

## Work already done

- Verified 281-file entry tree; 135 main commits in last 7 days, 238 in last 30/90 days; recent upload, gallery, health and AI API changes reviewed at history level.
- Fixed actual Makefile systemd-help line continuation and added an execution-based regression test.
- Corrected overstated readiness documentation in START/CURRENT_MODEL/DEPLOY.
- Removed obsolete absolute development directories from README/START, with isolation instructions.
- Minimal Linux Sandbox shell reproduction: old exit 2, corrected exit 0.
- No merge, production cutover, tag, database or media mutation. The `fix/disable-automatic-actions-20261105` branch remains unrelated and untouched.

## Next finite actions

1. **Read** preflight v2 and QA task results. Distinguish done/PASS, failed, incomplete/UNKNOWN, or pending. If QA failed, isolate the exact failing stage and repair only a newly demonstrated issue; do not weaken tests. If QA could not run, do not advertise a release-ready build.
2. Check current branch diff against current main, including the docs-only commits; review test changes and run the narrow docs/format gate appropriate to them.
3. Complete missing native/Chromium/dependency/security/clean-environment gates where available. Keep the live Samsung app, SQLite, photos, keys and Restic untouched except read-only probes.
4. Only after a clean exact-source gate and production-safe backups: review PR, guarded deployment of an immutable candidate, verify live readiness/public routes/rollback, then promote **the deployed SHA** to main and publish release tag through authorized release operator. This is **not** permission to deploy without evidence.
5. Update the checkpoint with exact resulting SHA, receipts and PASS/OPEN status; close only verified issues. No need to reopen the proven Makefile defect or old gallery audits without regression.

Operating prohibitions: no Codex, Work, GitHub Actions queries/execution, forced push, destructive worktree resets, silent device host switch, automatic deploy, production mutating API tests.
