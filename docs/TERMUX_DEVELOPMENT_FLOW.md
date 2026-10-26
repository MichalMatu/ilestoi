# IleStoi development: Samsung/Termux-first workflow

**Scope:** only `MichalMatu/ilestoi`. Do not apply this host rule to GrowClip,
Local Agent, Shelly Link or any other repository. Repository `AGENTS.md` is
the authority for this choice.

## Routing without project binding

Choose the existing Local Agent host task namespace directly:
`android-termux-10520` (installation
`6be16f1d-194b-4f07-b377-3d4bb218fcd7`). Normal host-task intake is
part of the **Local Agent installation**, not an IloStoi project binding.

For read, build and tests, publish immutable exactly addressed task JSON through
`MichalMatu/local-agent`, branch `agent-control`, at:

```text
.agent/hosts/android-termux-10520/supervisor/6be16f1d-194b-4f07-b377-3d4bb218fcd7/tasks/<unique-id>.json
```

Read matching `task-results/<unique-id>.json`; only an actual result with
`done`, command return code and observed output confirms success. Do not reuse
an ID after an UNKNOWN/outage, and never silently redirect a task to a Mac.
No `agent_binding`, repo registration, separate Git-control clone, or
`repo add --apply` is required for these machine-scoped tasks. The optional
repository-scoped worker remains available if explicitly requested later.

Use GitHub Connector for GitHub content, branches and PRs. Normal implementation
and test execution should be dispatched to **the Termux Agent** rather than
running code on a Mac. A Mac may be selected explicitly for unavailable browser
or native tooling, ideally without physical USB/SSH chaining.

## Source layout and safe worktrees

Existing production checkout:

```text
~/WreckScanner/WreckScanner
```

The parent `~/WreckScanner` is a *different Git repository*. Do not confuse
them. The nested application repo is currently the `work/dirty` development
source, but its working tree is also used by the running site: **never switch
branches, reset, clean, install build dependencies, run mutating tests, or
replace live files there**.

One-time separate development worktree, after verifying production Git status
and existing worktree catalog:

```sh
live="$HOME/WreckScanner/WreckScanner"
dev="$HOME/.local/state/ilestoi-dev/worktrees/feature"
git -C "$live" status --short --branch
git -C "$live" worktree list
mkdir -p "$(dirname "$dev")"
git -C "$live" worktree add --detach "$dev" HEAD
git -C "$dev" fetch --no-tags origin refs/heads/work/interactive-onboarding-20261026
git -C "$dev" switch --detach FETCH_HEAD
```

The worktree shares Git objects and avoids another full clone. Git commands
still change shared `.git` metadata, so **verify repository identity and
never change the branch or HEAD of the live checkout**. In an existing worktree,
verify it is clean before switching; do not overwrite owners' changes. For
future work prefer one appropriately named, reusable worktree per active feature.

On the isolated worktree:

```sh
cd "$dev"
node --test tests/js/onboarding_tour.test.mjs
python3 -m unittest discover -s tests -p 'test_onboarding_tour_frontend.py'
# Where dependencies are available, inside this worktree only:
npm ci --prefer-offline --ignore-scripts --no-audit --no-fund
npm run lint:web
npm run test:web
```

`node`, `npm`, Python 3.14 and Git exist on Termux. Chromium and
Playwright are **not installed on the phone** as of the 2026-10-26 preflight;
do not silently install large browser toolchains or assume macOS-equivalent
native dependencies. Escalate the *specific browser test* to the Mac only
when needed and report it separately.

## Running site and safeguards

Production owns `server.py`, SQLite, photos, secrets, Cloudflare
`ilestoi-phone` and the six separate application services supervised by
`runit`. Local Agent is a seventh, independent service. Preserve live
data and runtime; never run test fixtures against the live `127.0.0.1:8001`
database or HTTP write routes. Scope subprocesses, outputs, CPU/RAM and test
concurrency so the phone remains responsive.

Before/after work record the exact source commit of both production and
feature worktree and the `runit` health statuses. Production rollout is
**separate** from Git changes. If explicitly deploying, follow
[TERMUX.md](TERMUX.md), use an independent recoverable backup and confirm
local readiness and public HTTP success. Avoid auto-deploy on every Git push.

## Host-selection policy

- IleStoi: **Samsung Termux first** for code and local tests; Mac only for
  the missing browser or other clearly justified capability.
- Other repositories: retain their independent, previously selected host
  workflows. Do not infer a universal default from this document.
- Host selection is manual and explicit. No automatic scheduling, cross-host
  failover or background performance telemetry is introduced.
