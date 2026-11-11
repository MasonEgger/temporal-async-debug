# temporal-async-debug Implementation Plan (Event-Loop Exercises)

This plan turns the `event-loop-exercises` arc in `spec.md` into an executable, test-driven build sequence.
Each step is a literal prompt for a code-generation LLM.
Feature steps follow RED/GREEN/REFACTOR; Task steps follow Scope/Tooling/Do/Verify/Document.
Steps build strictly on their predecessors with no orphaned code.

Read `spec.md` in full before starting.
The source of truth is the `## Architecture` (Root package trim, Exercises, Observability, Documentation), `## Behavior requirements`, `## Exercise requirements`, `## Observability requirements`, `## Test requirements`, and `## Documentation requirements` sections, with the live mechanics in `## Starting context`.
Honor the fences in `## Invariants`, `## Non-goals`, and both `**Deferred:**` lists: the whole arc is about ONE mechanism, blocking the shared asyncio event loop; no slot-exhaustion, heartbeat-tuning, timeout-tuning, schedule-to-start, or retry-policy lesson, not even as a contrast case; `temporal server start-dev` only (never a cluster, a server container, or Cloud); the compose stack holds only Prometheus and Grafana; no new Python runtime dependency; the 102 `practice`/`solution` layout; a `solution/` copy carries no antipattern and no marker; every quoted block is a capture of its own exercise; no role-labeled names; no lab mode, no alert rules, no ProcessPoolExecutor exercise, no blocking-in-Workflow exercise, no Codespaces, no committed script that reproduces whole runs (the stdlib `scripts/receipt_gaps.py` helper from Section 9 is the one exception), no Web UI screenshots beyond exercise 02's (Section 9), no venue or frontmatter.

The arc TRIMS the shipped failure-mode catalog first (Section 1), then builds the observability stack and the gate harness, then the five exercises, then captures and prose.
The root package after the trim is what part 1 baselines and the source each exercise copy starts from.

## Current Status

- [ ] Section 0: Prose Tooling Pre-flight
  - [ ] Step 0: Vale Config, Prose Lint Recipes, And The Pre-flight Gate
- [ ] Section 1: Root Package Trim
  - [ ] Step 1: Trim The Root Package To The Frozen-Loop Reference
- [ ] Section 2: Observability Stack
  - [ ] Step 2: Observability Config And Its Tests
  - [ ] Step 3: Metrics And Server Just Recipes
- [ ] Section 3: Exercise Gate Harness
  - [ ] Step 4: The Per-Directory Solution Gate And Practice Lint Pass
- [ ] Section 4: The Five Exercises
  - [ ] Step 5: Exercise 01 Sync HTTP Client
  - [ ] Step 6: Exercise 02 Sleep Between Heartbeats
  - [ ] Step 7: Exercise 03 CPU Bound
  - [ ] Step 8: Exercise 04 Zombie Thread
  - [ ] Step 9: Exercise 05 Catching Blockers Early
- [ ] Section 5: Live Captures
  - [ ] Step 10: Capture Before And After For Every Exercise Plus The Baseline
- [ ] Section 6: Exercise READMEs
  - [ ] Step 11: Write The Five Exercise READMEs From The Captures
- [ ] Section 7: Tutorial Series Drafts
  - [ ] Step 12: Write The Six-Part Series Drafts
- [ ] Section 8: Root Documentation Refresh
  - [ ] Step 13: Root README, CLAUDE.md, And docs/drafts/README Refresh
- [ ] Section 9: Post-Review Rework
  - [ ] Step 14: Reconcile spec.md, plan.md, And .vale.ini With The Rulings
  - [ ] Step 15: Commit The Receipt-Gap Helper
  - [ ] Step 16: Exercise 03 Metrics-Port Setting
  - [ ] Step 17: Rebuild Exercise 02 For A Visible Retry Storm
  - [ ] Step 18: Exercise 05 Realistic Audit Trail
  - [ ] Step 19: Recapture For The Rework
- [ ] Section 10: Rework Prose
  - [ ] Step 20: Update The Exercise READMEs
  - [ ] Step 21: Update The Series Drafts
  - [ ] Step 22: Update The Root README And CLAUDE.md

## Architecture Recap (target for this arc)

One mechanism: blocking the shared asyncio event loop from an `async def` Activity.
Three layers, with the root package trimmed in place and the other two new:

- Root package (`src/temporal_async_debug/`): trimmed to the frozen-loop reference. `block` and `cpu` modes, the healthy path, the bystander fleet (receipt, rollup), the freeze ordering with the `get_location` STARTED gate, the `os._exit(0)` teardown, the Prometheus endpoint on 127.0.0.1:9464. Everything about saturation, heartbeats, schedule-to-start, the quote, and `maximum_attempts=1` is removed. Baselined by part 1 and quoted by the root README's three lessons.
- Exercises (`exercises/NN-name/{README.md,practice/,solution/}`): five standalone flat copies in the 102 shape, one per common way developers block the loop. A copy holds `shared.py`, `activities.py`, `workflow.py`, `receipt.py`, `rollup.py`, `worker.py`, `starter.py`, and `tests/`, plus any exercise-named file, runs from its own directory with `uv run python worker.py` and `uv run python starter.py ...` under the root virtual environment, and imports its siblings as flat top-level modules (`import shared`, resolved because the copy's own directory is on `sys.path` when run from there). `practice/` keeps the antipattern and its marker and adds `# TODO PART X:` comments at every edit point plus a `TODO PART D` test stub; `solution/` has the fix, no antipattern, no marker, and the reader's test implemented and green.
- Observability (`observability/`): a `docker-compose` v1 stack of Prometheus and Grafana only, scraping the SDK endpoint on 127.0.0.1:9464 and the dev server endpoint on 127.0.0.1:9465, with a provisioned datasource and one provisioned dashboard.

The five exercises, in order of how often Temporal users hit them (from spec Architecture; confirm the per-exercise decisions at review).
Every exercise clears the same bar: the code's execution misbehaves in a way the reader sees without a dashboard (bystanders fail, attempts fail and retry, the same work runs twice, a bystander is visibly delayed on every run), and the Python tooling the reader runs (`python -m asyncio ps`, `pstree`, `py-spy dump`, the CPU reading, asyncio debug mode) names the cause.
A metrics blip alone does not qualify as the bug; Grafana corroborates what the tooling found and is never the lesson.
Each exercise presents as a mystery the reader debugs: Part A makes it misbehave, Part B reaches for the tool, and the tool points at the line.

| Exercise | The bug (kept in practice, marked) | The failure the reader sees, and the tool that names it | The fix (solution, no marker) | Part D test |
|---|---|---|---|---|
| 01-sync-http-client | `async def` `get_ip`/`get_location` calling a synchronous `httpx.Client`; the bad run's input points at a local slow endpoint | The healthy fleet hits fast providers and completes, so nothing looks wrong (the bug hides); pointed at the local slow endpoint, the loop freezes, the in-flight rollup fails its timeout, and receipts stall until the thaw. `asyncio ps` shows one task dead-ended at the SDK handler, `py-spy dump` names the `httpx.Client` call, CPU sits near zero. | plain `def` activities on the same sync client; `worker.py` passes `activity_executor=ThreadPoolExecutor(max_workers=max_concurrent_activities)` | probe: a 50 ms ticker beside the activity is not starved |
| 02-sleep-between-heartbeats | `async def` activity polling a slow job: an awaited async status check, then `activity.heartbeat()` and a blocking `time.sleep(poll_interval)` once per poll, with `poll_interval` (8 s) longer than the fixed `heartbeat_timeout` (5 s) and a 60 s job keyed on the run id | A visible retry storm. The heartbeat recorded before the sleep is an asyncio task that cannot run while the loop is frozen, so the server fails each attempt on Heartbeat timeout; cancels land late, so failed attempts keep polling as overlapping zombies while the default retry policy starts the next attempt. The `Attempt` counter climbs past 2 in the Web UI pending-activity view and in `temporal workflow describe` (workflow show writes no event per retried attempt), the Worker log keeps printing dead attempts' poll lines and shows `TMPRL1101 Potential deadlock detected` (a frozen-loop clue), bystanders fail or stall, the run completes after about 65 s, and `py-spy dump` names the `time.sleep` line. Web UI screenshots are allowed for this exercise. | wait in awaited 1-second ticks with a heartbeat each tick (`activity.heartbeat()` then `await asyncio.sleep(1)` until the next poll is due), so heartbeats flush on the loop more often than the timeout and cancellation lands at the await | `ActivityEnvironment` run asserts more than one heartbeat reaches the environment during a single poll wait, and an unstarved probe beside it |
| 03-cpu-bound | `async def` activity doing pure-Python computation that holds the GIL and pins CPU | The frozen-loop shape of 01 (dead-ended task, bystanders fail) with the one reading that separates the two causes: `top` at about 100 percent on one core where 01 sat near zero; `py-spy dump` shows the compute loop on the main thread. The work is bounded by the input's size, so a run pins one core for a fixed stretch and nothing more. | the `def` plus executor change from 01; work runs on a pool thread | probe: the 50 ms ticker is not starved |
| 04-zombie-thread | an `async def` activity that wraps the blocker in `asyncio.to_thread(...)` under a `heartbeat_timeout` with no heartbeat, the fix most users ship first because it looks right: the loop is live and the bystanders are fine | The activity runs twice. When the server times the attempt out, the coroutine is cancelled but the detached thread keeps running to completion, and the retry starts the same work beside it; the Worker log shows the first thread finishing after its attempt already failed and the retry's work overlapping it (duplicate side effects), and `py-spy dump` shows the orphaned thread still inside the blocker after the failure. | a `def` activity on a `ThreadPoolExecutor` sized to `max_concurrent_activities` that heartbeats from its own thread, so a timeout or cancel arrives as `CancelledError` inside the thread and the work stops | `ActivityEnvironment` cancel of the `def` activity asserts the work stops at the next heartbeat; plus a `build_worker` assertion that `max_workers` >= `max_concurrent_activities` |
| 05-catching-blockers-early | one `zlib.compress` (level 9) over seeded, generated audit-log lines in an `async def` activity that stalls the loop about 350 ms on every run (zlib releases the GIL, so the `to_thread` fix visibly recovers) | Nothing times out, which is the point of this one: the blocker that has not taken anything down yet. The execution still misbehaves: every bystander dispatched into the stall waits it out, so the receipts' first Workflow Task gap is 298 to 394 ms here against 19 to 23 ms in the healthy fleet, visible in `temporal workflow show`; asyncio debug mode logs the slow-callback warning, which names the SDK handler `_ActivityWorker._handle_start_activity_task`, and `py-spy dump` names the `zlib.compress` line. The README notes that a real archiver uploads the bytes and returns a blob-storage key. The one detection lesson in the series. | move the work off the loop | the probe test parametrized over every registered `async def` activity |

All five copies carry the bystander fleet (receipt, rollup) and the starter's freeze ordering, so the cross-type blast radius reads the same way in every exercise.

Antipattern marker convention (fixed, greppable), on or immediately above each offending line:

```
# ANTIPATTERN (deliberate, for teaching): <why it is wrong>. Correct: <the right approach>. Do not copy.
```

`grep -rn "ANTIPATTERN (deliberate, for teaching)" exercises/*/solution` must return nothing.

## Section 0: Prose Tooling Pre-flight

**Tools:**
- Skills: content-design:style-linting
- MCPs: none
- Linters: just preflight

### Step 0: Vale Config, Prose Lint Recipes, And The Pre-flight Gate (task)

**NOTE**: Sections 6, 7, and 8 write prose that must be Vale-clean under MasonBase plus MasonTechnical, and their validators run Vale as a declared linter.
The repo has no `.vale.ini`, so Vale falls back to `~/.vale.ini`, whose MasonTechnical glob (`{tutorials,tutorial,technical,how-to,howto}/**`) matches nothing in this tree; `docs/drafts/*.md` and `exercises/*/README.md` would get MasonBase only.
A validator whose declared linter cannot run records a note instead of a finding (validator-protocol.md, "Linter-sourced findings"), so a missing or wrong Vale setup fails silently.
This step runs first so the prose gate exists and is proven before any code step, and long before a prose step depends on it.
The config below was verified on 2026-11-03 with Vale 3.21.0, `StylesPath = /home/mmegger/Code/MasonEgger/vale-styles/styles`, and Std already synced: it fires `MasonTechnical.StepHeadings`, `MasonTechnical.Emoji`, and `MasonTechnical.SentenceLength` on `docs/drafts/tutorial-original-draft.md`, and `--output=JSON` parses.
Both plugin roots are resolved by glob at run time (`content-design/*/`, `voice/*/`, newest version wins), never pinned to a version number.

```text
1. Scope:
   - Artifact(s): .vale.ini (new, repo root), justfile (three new recipes: preflight, lint-prose, lint-keyboard)
   - Desired end state: `just preflight` exits 0 on this machine and prints one `ok ...` line per check; `just lint-prose` runs Vale with JSON output over the files named as arguments, or with no arguments over every committed prose file this arc produces (existing files only, never docs/drafts/tutorial-original-draft.md); `just lint-keyboard` runs the content-design keyboard-characters check the same way; `vale ls-config` from the repo root shows MasonTechnical applied to docs/drafts/** and exercises/**; `just check` is unchanged and still exits 0.

2. Tooling:
   - Skills: content-design:style-linting (the .vale.ini shape, the Std sync rule, and how to read Vale output)
   - MCPs: none
   - External: vale 3.20 or newer; the content-design plugin's scripts/normalize-keyboard-chars.py and skills/tutorial-writing/scripts/wordcount; the voice plugin's skills/teaching/SKILL.md and skills/voice/references/profile.md; uv

3. Do the work:
   - Create .vale.ini at the repo root with exactly this content (it mirrors the global template's StylesPath, Packages, ignores, and the technical-writing section, with the globs this tree actually uses):

     StylesPath = /home/mmegger/Code/MasonEgger/vale-styles/styles
     Packages = Std

     # error | warning | suggestion
     MinAlertLevel = suggestion

     # --- Defaults: root README, CLAUDE.md, anything not matched below ------
     [*.{md,rst}]
     BasedOnStyles = MasonBase
     BlockIgnores = (?s) *(```.*?```)
     TokenIgnores = (\x60[^\n\x60]+\x60)

     # --- Technical writing: exercise READMEs and the tutorial drafts ------
     # Same layer as ~/.vale.ini's tutorials section; the globs name this tree.
     [{docs/drafts,exercises}/**/*.md]
     BasedOnStyles = MasonBase, MasonTechnical
     MasonBase.We = suggestion
     MasonTechnical.SentenceLength[max] = 25
     BlockIgnores = (?s) *(```.*?```)
     TokenIgnores = (\x60[^\n\x60]+\x60)

   - Add these three recipes to the justfile directly after the `test` recipe (shebang recipes, so each body runs as one bash script):

     # Verify the prose toolchain Sections 6 to 8 depend on: Vale, the Mason styles, Std, the content-design and voice plugin files
     preflight:
         #!/usr/bin/env bash
         set -euo pipefail
         fail() { echo "preflight: $1" >&2; exit 1; }
         command -v vale >/dev/null || fail "vale is not on PATH"
         ver=$(vale --version | awk '{print $3}')
         python3 -c "import sys; v=tuple(int(x) for x in '$ver'.split('.')[:2]); sys.exit(0 if v >= (3, 20) else 1)" || fail "vale $ver is older than 3.20"
         echo "ok vale $ver"
         [ -f .vale.ini ] || fail ".vale.ini missing at the repo root"
         styles=$(awk -F' = ' '/^StylesPath/ {print $2}' .vale.ini)
         [ -d "$styles" ] || fail "StylesPath $styles does not exist"
         for style in MasonBase MasonTechnical; do
             [ -d "$styles/$style" ] || fail "style $style missing under $styles"
             echo "ok style $style"
         done
         [ -d "$styles/Std" ] || vale sync
         [ -d "$styles/Std" ] || fail "Std not present after vale sync"
         echo "ok Std"
         vale ls-config | grep -q MasonTechnical || fail ".vale.ini does not apply MasonTechnical"
         echo "ok .vale.ini applies MasonTechnical"
         vale --no-exit --output=JSON docs/drafts/README.md | python3 -c 'import json, sys; json.load(sys.stdin)' || fail "vale JSON output did not parse"
         echo "ok vale JSON output"
         cd_root=$(ls -d "$HOME"/.claude/plugins/cache/mmegger-private-plugins/content-design/*/ 2>/dev/null | sort -V | tail -1)
         [ -n "$cd_root" ] || fail "content-design plugin not found under ~/.claude/plugins/cache"
         [ -f "$cd_root/skills/tutorial-writing/SKILL.md" ] || fail "tutorial-writing skill missing"
         [ -f "$cd_root/commands/review-content.md" ] || fail "review-content command missing"
         echo "ok content-design skills"
         rc=0; uv run "$cd_root/scripts/normalize-keyboard-chars.py" --check docs/drafts/README.md >/dev/null || rc=$?
         [ "$rc" -le 1 ] || fail "normalize-keyboard-chars.py did not run (exit $rc)"
         echo "ok keyboard-characters script"
         "$cd_root/skills/tutorial-writing/scripts/wordcount" docs/drafts/README.md >/dev/null || fail "wordcount script did not run"
         echo "ok wordcount script"
         voice_root=$(ls -d "$HOME"/.claude/plugins/cache/mmegger-private-plugins/voice/*/ 2>/dev/null | sort -V | tail -1)
         [ -n "$voice_root" ] || fail "voice plugin not found under ~/.claude/plugins/cache"
         [ -f "$voice_root/skills/teaching/SKILL.md" ] || fail "voice:teaching skill missing"
         [ -f "$voice_root/skills/voice/references/profile.md" ] || fail "voice profile missing"
         echo "ok voice:teaching skill and profile"
         echo "preflight: all checks passed"

     # Lint prose with Vale as JSON for the validator: the named files, or every committed prose file this arc produces (never the provenance draft)
     lint-prose *files:
         #!/usr/bin/env bash
         set -uo pipefail
         files="{{files}}"
         [ -n "$files" ] || files=$(ls README.md CLAUDE.md docs/drafts/README.md docs/drafts/part-*.md exercises/*/README.md 2>/dev/null || true)
         [ -n "$files" ] || { echo '{}'; exit 0; }
         vale --no-exit --output=JSON $files

     # Flag non-keyboard characters (em-dashes, smart quotes, arrows, emoji): the named files, or the same default set
     lint-keyboard *files:
         #!/usr/bin/env bash
         set -uo pipefail
         files="{{files}}"
         [ -n "$files" ] || files=$(ls README.md CLAUDE.md docs/drafts/README.md docs/drafts/part-*.md exercises/*/README.md 2>/dev/null || true)
         [ -n "$files" ] || { echo "no prose files yet"; exit 0; }
         cd_root=$(ls -d "$HOME"/.claude/plugins/cache/mmegger-private-plugins/content-design/*/ | sort -V | tail -1)
         uv run "$cd_root/scripts/normalize-keyboard-chars.py" --check $files

   - Run `just preflight` and fix whatever it reports until it exits 0. Never weaken a check to make it pass; a missing style directory, an unsynced Std, or a missing plugin file is a Failure for this step, not something to route around.

4. Verify:
   - `just preflight` exits 0 and prints every `ok` line; `vale ls-config` from the repo root lists MasonTechnical under the `{docs/drafts,exercises}/**/*.md` glob; `just lint-prose` exits 0 and emits JSON (with no arguments it covers README.md, CLAUDE.md, and docs/drafts/README.md today, since no part or exercise README exists yet); `just lint-prose docs/drafts/README.md` emits JSON for that one file; `just lint-keyboard` exits 0 both ways; bare `just` lists the three new recipes; `just check` exits 0 unchanged.

5. Document:
   - Recipe comments only. The README and CLAUDE.md recipe tables are refreshed in Step 13 and must list preflight, lint-prose, and lint-keyboard there.
```

## Section 1: Root Package Trim

**Tools:**
- Skills: python:python, temporal:temporal-developer
- MCPs: mcp__temporal-docs__search_temporal_knowledge_sources
- Linters: uv run ruff check --output-format=json ., uv run mypy .

The trim changes behavior (modes and timeouts removed), so the validator should confirm the surviving `block`/`cpu` behavior and freeze ordering still match the Behavior requirements and that no saturation, heartbeat, or retry-policy code survives.

### Step 1: Trim The Root Package To The Frozen-Loop Reference

**NOTE**: This step removes everything that is not the frozen loop from the shipped catalog package, and deletes the tests for the removed code rather than skipping them.
The surviving behavior is exactly the `block` and `cpu` scenarios plus the healthy baseline in `## Behavior requirements`, with the bystander fleet (receipt, rollup), the freeze ordering gated on `get_location` STARTED plus 1 second, and the `os._exit(0)` teardown.
Confirm the sync-versus-async and default-retry-policy behavior against the temporal-docs MCP before changing `workflow.py`.
The `max_concurrent_activities=2` setting STAYS (so the freeze-lesson slot readings stay small and readable) but is no longer an antipattern: remove its marker and replace it with a plain comment saying the small size is deliberate for a single-machine demo (decision: keep 2 and drop the marker; confirm at review).

```text
1. RED: Update the root test suite to the trimmed surface first:
   - In tests/test_shared.py, change the VALID_MODES assertion to expect exactly {"block", "cpu"} (drop slow, slow_heartbeat, stuck_no_heartbeat), and remove any assertions about quote dataclasses.
   - In tests/test_activities.py, keep the block and cpu and healthy and failover cases; DELETE the test cases for slow, slow_heartbeat, and stuck_no_heartbeat (not skip, delete).
   - In tests/test_starvation_probe.py, keep the block and cpu starve-the-probe cases and the healthy does-not-starve case; DELETE the slow and slow_heartbeat cases.
   - In tests/test_workflow.py, change the geo_activity_options expectations to a single fixed set (start_to_close 120s, schedule_to_close 150s, no heartbeat_timeout, no RetryPolicy maximum_attempts); keep the unknown-mode ApplicationError(type="InvalidMode") case; remove any case asserting maximum_attempts=1 surfaces a failure.
   - In tests/test_worker.py, change the build_worker assertion to expect max_concurrent_activities == 2 and registration of GeoEnrichmentWorkflow, OrderReceiptWorkflow, SalesRollupWorkflow and their activities only (NO PriceQuoteWorkflow).
   - In tests/test_starter.py, DELETE the saturation-ordering and SATURATION_MODES and --quotes cases; keep fleet_from_args and the freeze submission-order cases (geo, receipt, rollup only).
   - DELETE tests/test_quote.py and tests/test_geo_options.py cases that only cover removed timeouts; keep tests/history.py (used again by exercises) and tests/test_rollup.py and tests/test_receipt.py.
   - These edits assert the trimmed public surface (modes, timeouts, registration, ordering); run `just check` and confirm it now FAILS against the untrimmed source.

2. Document component:
   - Update module docstrings in activities.py, workflow.py, worker.py, and starter.py to describe the frozen-loop reference (block and cpu only) rather than the full catalog.

3. GREEN: Trim the source to make the updated tests pass:
   - shared.py: set VALID_MODES to ("block", "cpu"); delete the PriceQuote input/output dataclasses.
   - activities.py: in _apply_mode keep only the block branch (time.sleep, marker kept) and the cpu branch (busy loop, marker kept); delete the slow, slow_heartbeat, and stuck_no_heartbeat branches and the _heartbeat_before_provider_attempt helper; keep get_ip, get_location, the provider rotation and failover, and HTTP_TIMEOUT_SECONDS.
   - workflow.py: collapse geo_activity_options to one fixed GeoActivityOptions (start_to_close 120s, schedule_to_close 150s, no heartbeat_timeout); delete the RetryPolicy(maximum_attempts=1) and its marker so the geo activities use the default retry policy; keep the ApplicationError(type="InvalidMode") raise.
   - quote.py: delete the file.
   - worker.py: drop PriceQuoteWorkflow from registration; keep max_concurrent_activities=2 but remove its antipattern marker and add a plain comment that the small size is deliberate for a single-machine demo; keep the Prometheus endpoint on 127.0.0.1:9464 and the PID banner.
   - starter.py: delete SATURATION_MODES, the saturation ordering function, the concurrent fallback that only served saturation modes, the --quotes argument, quote_inputs_from_args, _start_quotes, and quote references in Fleet and reporting; keep fleet_from_args, the freeze ordering with the get_location STARTED gate plus 1-second guard, the geo/receipt/rollup batches, and os._exit(0).
   - Confirm `grep -rn "slow_heartbeat\|stuck_no_heartbeat\|PriceQuote\|maximum_attempts\|SATURATION" src tests` returns nothing.

4. RED: Add a guard test:
   - In tests/test_shared.py (or a small tests/test_scope.py), assert that importing temporal_async_debug.quote raises ModuleNotFoundError and that shared.VALID_MODES has length 2, so a regression that re-adds the removed surface fails.

5. GREEN: Confirm the guard passes (the quote module is gone, VALID_MODES is {"block","cpu"}).

6. REFACTOR: Remove now-dead imports, constants, and helpers left by the trim; keep the block and cpu markers exactly in the fixed format; keep each surviving module small and readable.

7. Update documentation:
   - none here; the root README and CLAUDE.md are refreshed in Step 13, and the README's three lessons are recaptured in Step 10.

8. Verify the trimmed suite covers block, cpu, healthy, failover, the fixed timeouts, the registration without the quote, and the freeze ordering; confirm `grep -rn "ANTIPATTERN (deliberate, for teaching)" src` returns exactly the block and cpu markers; run `just check`.
```

## Section 2: Observability Stack

**Tools:**
- Skills: python:python
- MCPs: none
- Linters: uv run ruff check --output-format=json ., uv run mypy .

No session skill or MCP covers Prometheus or Grafana, so what the validator can hold onto here is the config tests and the invariant that the compose file defines no Temporal server service; the metric names are verified live in Step 10, not by a tool here.

### Step 2: Observability Config And Its Tests

**NOTE**: This step writes the `observability/` stack and the Python config tests that pin its shape, with no live server involved.
The dashboard panels show what a frozen loop does to the Worker over time (from spec Architecture): `temporal_activity_execution_latency`, the workflow-task latencies, activity and workflow task failures and timeouts, `temporal_worker_task_slots_used` by `worker_type`, and the dev server's Task Queue backlog.
The exact metric names and the backlog panel are confirmed or dropped live in Step 10, so the allowlist test must accept the stack with a panel removed too.
The config tests live under the root `tests/` tree and run in the existing root pytest, so they need no new gate wiring.

```text
1. RED: Write the observability config tests first, and test only the stack's invariants (never that a file parses or that a library works; parsing is how a test reads the file, not what it asserts):
   - Create tests/test_observability_config.py:
     - Test that observability/docker-compose.yml defines exactly the services {"prometheus", "grafana"} and that no service's image string contains the substring "temporal" (the invariant: the compose stack never runs a Temporal server).
     - Test that observability/prometheus.yml scrapes exactly the two targets "127.0.0.1:9464" and "127.0.0.1:9465" and nothing else (the SDK endpoint and the dev server endpoint the lessons read).
     - Test that every panel target expression in observability/grafana/dashboards/*.json (walk panels[].targets[].expr) references only metric names from an allowlist = {"temporal_activity_execution_latency", "temporal_workflow_task_schedule_to_start_latency", "temporal_workflow_task_execution_latency", "temporal_worker_task_slots_used", "temporal_activity_execution_failed", "temporal_activity_execution_latency_count"} plus any name beginning "temporal_" that the test treats as the optional dev-server backlog gauge; the test must still pass if the backlog panel is later removed.
     - Read YAML with a parser already in the dev dependency group if one exists; otherwise a minimal hand-parse of the keys these tests need. Do NOT add a runtime dependency, and do not add a dev dependency only to parse a file.
   - No test for the scrape interval, the image tags, the Grafana environment variables, the panel count, or that JSON loads: those are configuration choices, not logic. Three tests plus the Step 4 consistency test is the whole file.

2. Document component:
   - Add a one-paragraph header comment to observability/docker-compose.yml and observability/prometheus.yml stating that the stack is Prometheus and Grafana only, docker-compose v1 syntax, host networking on Linux, and that it scrapes the SDK (9464) and dev server (9465) endpoints.

3. GREEN: Write MINIMAL config to make the tests pass:
   - Create observability/docker-compose.yml (v1-compatible schema, no "docker compose" v2-only keys): a prometheus service (official prometheus image, mounts ./prometheus.yml, network_mode: host so it reaches 127.0.0.1 endpoints on Linux) and a grafana service (official grafana image, network_mode: host, anonymous viewer access via GF_AUTH_ANONYMOUS_ENABLED and GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer, mounts ./grafana/provisioning and ./grafana/dashboards). No other services.
   - Create observability/prometheus.yml: global scrape_interval 5s; one scrape_config with two static_configs targets 127.0.0.1:9464 and 127.0.0.1:9465.
   - Create observability/grafana/provisioning/datasources/prometheus.yml: a Prometheus datasource pointing at http://localhost:9090, set default.
   - Create observability/grafana/provisioning/dashboards/dashboards.yml: a file provider loading the mounted dashboards path.
   - Create observability/grafana/dashboards/async-debug.json: a dashboard with panels for activity execution latency, workflow-task schedule-to-start and execution latency, activity and workflow task failures/timeouts, task slots used by worker_type, and a Task Queue backlog panel using the dev server backlog gauge (leave its expr using the expected backlog metric name; Step 10 confirms or drops it). Every panel expr references only allowlisted metrics.

4. RED: Add a cross-file consistency test:
   - In tests/test_observability_config.py, assert that the dashboards provider path in grafana/provisioning/dashboards/dashboards.yml matches the container path the compose file mounts observability/grafana/dashboards to, so a provisioning path typo fails the gate.

5. GREEN: Align the mount path and provider path so the consistency test passes.

6. REFACTOR: Keep the YAML and JSON minimal and readable; no stray services, no commented-out blocks.

7. Update documentation:
   - none here (the Observability README section is Step 13).

8. Verify the config tests cover the two-service invariant, the two scrape targets, and the metric allowlist, then run `just check`.
```

### Step 3: Metrics And Server Just Recipes (task)

**Tools:** none

**NOTE**: Wiring, so Task template.
The justfile already has server, worker, and the surviving scenario recipes (healthy, trigger, block, cpu after Step 1).
This step points `just server` at the dev server metrics port and adds the two compose recipes.
docker-compose v1 only (no `docker compose` v2 plugin on the capture machine).

```text
1. Scope:
   - Artifact(s): justfile (edit)
   - Desired end state: `just server` runs `temporal server start-dev --metrics-port 9465` (confirm 9465 at review); `just metrics` runs `docker-compose -f observability/docker-compose.yml up -d`; `just metrics-down` runs `docker-compose -f observability/docker-compose.yml down`; the default (`@just --list`) recipe stays first; `just --list` and `just check` both exit 0.

2. Tooling:
   - Skills: none
   - MCPs: none
   - External: just, docker-compose (v1)

3. Do the work:
   - Edit the existing `server` recipe to append `--metrics-port 9465` to `temporal server start-dev`.
   - Add `metrics:` running `docker-compose -f observability/docker-compose.yml up -d`.
   - Add `metrics-down:` running `docker-compose -f observability/docker-compose.yml down`.
   - Keep `default` (`@just --list`) as the FIRST recipe; add the new recipes below it.

4. Verify:
   - Run bare `just` and confirm it prints the recipe list; run `just --list` and confirm server, metrics, and metrics-down appear and parse; run `just check` and confirm exit 0. (Bringing the stack up is a live step in Step 10, not here.)

5. Document:
   - none here; the Observability README section is Step 13.
```

## Section 3: Exercise Gate Harness

**Tools:**
- Skills: python:python
- MCPs: none
- Linters: uv run ruff check --output-format=json ., uv run mypy .

### Step 4: The Per-Directory Solution Gate And Practice Lint Pass (task)

**NOTE**: Wiring plus pyproject config, so Task template, but it establishes the gate every exercise step plugs into.
The near-identical module names across copies must never share one mypy or pytest invocation, so the root gate excludes `exercises/` entirely and each copy is checked in its own directory (confirm the loop shape at review).
The loop must be a no-op that exits 0 when no exercise directories exist yet, so the gate is green before Step 5 and after.

```text
1. Scope:
   - Artifact(s): justfile (edit), pyproject.toml (edit)
   - Desired end state:
     - Root ruff, ruff format --check, mypy, and pytest all exclude exercises/ (via ruff extend-exclude, mypy exclude, and pytest testpaths or --ignore).
     - `just check` runs the root gate (ruff check, ruff format --check, mypy strict, pytest) AND THEN a loop over every exercises/*/solution directory running, per directory, `uv run ruff check <dir>`, `uv run ruff format --check <dir>`, `uv run mypy <dir>`, and `uv run pytest <dir>/tests`; the loop exits 0 when no such directory exists.
     - `just check-practice` loops over every exercises/*/practice directory running `uv run ruff check <dir>` and `uv run mypy <dir>` only (practice carries the deliberate bug and the reader's unimplemented test, so it is not pytest-gated); it too exits 0 when none exist.

2. Tooling:
   - Skills: python:python (pyproject config shape)
   - MCPs: none
   - External: uv, ruff, mypy, pytest, just

3. Do the work:
   - In pyproject.toml, exclude exercises/ from ruff (extend-exclude), from mypy (exclude regex), and from pytest collection (set testpaths to the root tests dir, or add --ignore=exercises), keeping the canonical config blocks otherwise verbatim per the python skill.
   - In the justfile, extend the `check` recipe: after the existing root gate, add a bash loop over exercises/*/solution that runs the four per-directory commands above and fails fast on any non-zero; guard with nullglob or an existence test so zero directories is success.
   - Add a `check-practice` recipe with the analogous loop over exercises/*/practice running ruff check and mypy only.
   - Keep the `default` recipe first.

4. Verify:
   - Run `just check` with no exercises/ directory present and confirm exit 0 (root gate green, loop a no-op). Run `just check-practice` and confirm exit 0. Confirm `just --list` shows check-practice.

5. Document:
   - none here; CLAUDE.md's gate description is refreshed in Step 13.
```

## Section 4: The Five Exercises

**Tools:**
- Skills: python:python, temporal:temporal-developer
- MCPs: mcp__temporal-docs__search_temporal_knowledge_sources
- Linters: uv run ruff check --output-format=json ., uv run mypy .

Each exercise step produces a `practice/` copy (bug kept and marked, `# TODO PART X:` comments, a `TODO PART D` test stub) and a `solution/` copy (fix applied, no marker, Part D test implemented and green), both runnable from their own directory under the root virtual environment.
The exercise README is NOT written here; it is written from captures in Step 11, so these steps leave only module docstrings and the TODO comments, not prose lessons.
Consult the temporal-docs MCP to confirm the sync-activity-on-executor pattern (01, 03, 04), the heartbeat-from-a-thread pattern (04), and `asyncio` cancellation semantics (02, 04) before applying each fix.

### Step 5: Exercise 01 Sync HTTP Client

**NOTE**: This is the template copy the later exercises follow.
The copy is flat: sibling modules import each other as top-level names (`import shared`, `from activities import get_ip`), which resolve because the copy runs from its own directory.
The bug is an `async def` activity calling a synchronous `httpx.Client`; the healthy runs hit the real providers and are fast, so the bug hides, and the bad run's input points the provider at a local slow endpoint.
This is the sneaky one, and the README should say so: nothing in the healthy fleet looks wrong, the tests pass, and the Worker ships; the loop only freezes once a provider slows down, which is how this bug reaches production and why it is the first exercise.
The slow endpoint is a stdlib `http.server` the starter serves on 127.0.0.1 for the run's duration, in `slow_upstream.py` (decision: served by the starter so the reader needs no extra terminal; confirm at review).
The fix follows Temporal's sync-versus-async guidance: synchronous `def` activities on the Worker's `activity_executor` (a ThreadPoolExecutor sized to max_concurrent_activities).

```text
1. RED: Create the solution copy and write its failing Part D test first:
   - Create exercises/01-sync-http-client/solution/ as a flat copy of the trimmed root modules needed for this exercise: shared.py, activities.py, workflow.py, receipt.py, rollup.py, worker.py, starter.py, slow_upstream.py, and tests/ with a conftest.py mirroring the root test fixtures (network mock, deterministic provider rotation).
     - Rewrite every intra-package import from temporal_async_debug.X to the flat module name X.
     - Replace the block/cpu mode switch in activities.py with this exercise's shape: get_ip and get_location call a synchronous httpx.Client; the input carries an optional slow-upstream base URL that, when set, routes the provider call at the local slow endpoint.
     - Create solution/slow_upstream.py: a stdlib http.server handler that sleeps a configured number of seconds before responding, startable and stoppable by the starter on 127.0.0.1.
     - Trim starter.py to the freeze ordering for this exercise (healthy geo first, then the bad run pointed at the slow endpoint, then receipts gated on get_location STARTED plus 1 second), starting and stopping slow_upstream around the run.
   - Create exercises/01-sync-http-client/solution/tests/test_probe.py: the 50 ms ticker probe pattern from the root tests/test_starvation_probe.py, asserting that running the geo activity body (pointed at an in-test stdlib slow server, never the network) on the worker's activity_executor does NOT starve a 50 ms probe (every consecutive gap < 0.2 s). Written to fail now, because the activities are still async def calling the sync client on the loop.
   - This tests our fix (sync activities on the executor keep the loop live), not asyncio internals.

2. Document component:
   - Add module docstrings to the solution copy's activities.py and worker.py noting this is the 01-sync-http-client exercise copy and that the geo activities run synchronously on the worker's activity_executor.

3. GREEN: Apply the fix in the solution copy so the probe test passes:
   - In solution/activities.py, convert get_ip and get_location to plain def activities using the synchronous httpx.Client (httpx is already present; no new dependency); NO antipattern marker (the sync client is correct on a pool thread now).
   - In solution/worker.py, pass activity_executor=concurrent.futures.ThreadPoolExecutor(max_workers=<max_concurrent_activities>) to the Worker, sized to max_concurrent_activities; keep the Prometheus endpoint and the PID banner.
   - Adjust workflow.py activity execution if the SDK requires it for sync activities (confirm via the temporal-docs MCP); keep get_ip then get_location ordering and the output shape.
   - Confirm `grep -rn "ANTIPATTERN" exercises/01-sync-http-client/solution` returns nothing.

4. Create the practice copy:
   - Create exercises/01-sync-http-client/practice/ as the SAME flat copy but BEFORE the fix: async def geo activities calling the synchronous httpx.Client on the loop, carrying the antipattern marker (why a sync client blocks the loop; correct: a def activity on an executor).
   - Add `# TODO PART C:` and `# TODO PART D:` comments at the lines the reader changes (the async def signatures and the worker's activity_executor argument), each naming what to do without giving the answer.
   - Create practice/tests/test_probe.py as a stub with a `# TODO PART D:` comment and a failing placeholder, mirroring the solution test's intent but unimplemented.

5. Integrate into the gate:
   - Run `just check` and confirm the root gate stays green and the solution loop now checks exercises/01-sync-http-client/solution (ruff, ruff format, mypy, pytest including test_probe.py) at exit 0.
   - Run `just check-practice` and confirm exercises/01-sync-http-client/practice passes ruff and mypy (it parses and type-checks though it carries the bug and the stub).

6. REFACTOR: Keep both copies minimal and the diff between them limited to the fix lines and the TODO comments, so the tutorial can show a small, legible change.

7. Update documentation:
   - none (the exercise README is Step 11).

8. Verify the solution probe test has teeth (it fails if the activities are reverted to async def calling the sync client on the loop), revert to the fixed form, then run `just check` and `just check-practice`.
```

### Step 6: Exercise 02 Sleep Between Heartbeats

**NOTE**: Follows the Step 5 template.
The bug is an `async def` activity that polls a slow job in a loop, calling `activity.heartbeat()` and then `time.sleep(poll_interval)` once per poll, under a fixed `heartbeat_timeout` that is shorter than the poll interval (decision: `heartbeat_timeout` 5 seconds, `poll_interval` 8 seconds, a job that takes about 20 seconds; confirm at review).
On an `async def` activity, `activity.heartbeat()` schedules an asyncio task to send the heartbeat, so a heartbeat recorded right before `time.sleep` cannot leave the Worker until the sleep ends, and the server fails the attempt on Heartbeat timeout first.
What the reader sees in Part A is a retry storm: when the loop thaws, the SDK cancels the failed attempt's task, but asyncio cancellation only lands at an await and there is none, so the attempt keeps polling as a zombie (the Worker log keeps printing its poll lines after the failure) while the default retry policy starts the next attempt beside it, which freezes the loop the same way; `temporal workflow show` lists attempt after attempt ending in Heartbeat timeout, and the bystanders fail in the same windows (the cross-type blast radius).
The simulated slow job is keyed on the workflow run id (a module-level dict), so a retry observes the same job rather than starting a new one; the storm ends when the job finishes and the next attempt completes, which keeps the run bounded (a few failed attempts over roughly half a minute, then success).
The fix keeps the activity `async` and waits in awaited 1-second ticks with a heartbeat on each tick (`activity.heartbeat()` then `await asyncio.sleep(1)` until the next poll is due), so the heartbeats flush on the loop more often than the timeout and cancellation lands at the await (decision: this replaces the spec's one-line `await asyncio.sleep(poll_interval)`, which would still go 8 seconds without a heartbeat under a 5-second timeout; the `def` route is named in prose only; confirm at review).
This exercise is about the frozen loop, not heartbeat tuning: the heartbeat_timeout and the poll interval are fixed scenery, not values the reader changes.
Guard any heartbeat call reachable outside an activity with activity.in_activity() (a captured lesson), so the Part D ActivityEnvironment test can drive the loop.

```text
1. RED: Create exercises/02-sleep-between-heartbeats/solution/ as a flat copy, with the full bystander fleet, the freeze ordering, and the tests/ conftest mirroring the root fixtures.
   - Replace the activity body with the poll loop: get_location polls a simulated slow job keyed on the workflow run id, and between polls waits in awaited 1-second ticks, calling activity.heartbeat() (guarded by activity.in_activity()) on every tick, under the fixed heartbeat_timeout in workflow.py.
   - Create solution/tests/test_heartbeat.py: run the geo activity body under temporalio.testing.ActivityEnvironment with on_heartbeat counting calls and a 50 ms probe ticking beside it, with the job sized so one poll wait spans several ticks; assert the heartbeat count during a single poll wait is >= 2 AND the probe is not starved (every consecutive gap < 0.2 s). Written to fail against the still-time.sleep loop (one heartbeat per poll, and the probe starves).

2. Document component:
   - Module docstring on solution activities.py noting the 02-sleep-between-heartbeats copy and that the poll wait is awaited in short ticks with a heartbeat per tick, so heartbeats flush and cancellation lands.

3. GREEN: In solution/activities.py, replace the single time.sleep(poll_interval) with the awaited tick loop (activity.heartbeat() then await asyncio.sleep(1) until the next poll is due); keep the activity async def; REMOVE the antipattern marker; keep the fixed heartbeat_timeout in workflow.py; confirm `grep -rn "ANTIPATTERN" exercises/02-sleep-between-heartbeats/solution` returns nothing.

4. Create exercises/02-sleep-between-heartbeats/practice/: the SAME copy before the fix (one activity.heartbeat() then time.sleep(poll_interval) per poll, carrying the antipattern marker that says why the heartbeat cannot leave a frozen loop and why the cancel cannot interrupt the sleep), with a `# TODO PART C:` comment at the time.sleep line and a practice/tests/test_heartbeat.py stub carrying `# TODO PART D:`.

5. Integrate into the gate: `just check` checks the new solution dir green (including the heartbeat-count-and-probe assertion); `just check-practice` passes for the new practice dir.

6. REFACTOR: Keep the solution-versus-practice diff to the wait (one sleep line becomes the short tick loop) and the TODO comment.

7. Update documentation: none (README is Step 11).

8. Verify the test fails if the tick loop is reverted to the single time.sleep, revert to the awaiting form, then run `just check` and `just check-practice`.
```

### Step 7: Exercise 03 CPU Bound

**NOTE**: Follows the template.
The bug is pure-Python computation inside `async def` that holds the GIL and pins CPU; the fix is the same def-plus-executor change as 01, which keeps the loop live while the process still pins a core.
Recast the root cpu busy loop as a realistic transform of the provider response (for example a repeated hash or parse over the payload), not a bare `while True`.
The second-Worker-process demonstration is a README and capture concern (Steps 10 and 11), not code here; the copy just needs to run the cpu fleet correctly after the fix (confirm at review).
The CPU work is bounded: the bad run's input sets a fixed work size that pins one core for roughly the `block`-style duration and then returns, so it is safe on a laptop or a shared exercise machine (no unbounded spin, no fork, one core); the transform must take the size from the input, never loop until a wall-clock deadline.
What the reader sees is 01's frozen-loop shape (the dead-ended task in `asyncio ps`, the in-flight rollup failing, receipts stalling) plus the one reading that separates the two causes: `top` at about 100 percent on one core, where `time.sleep` sat near zero; `py-spy dump` shows the compute loop on the main thread.

```text
1. RED: Create exercises/03-cpu-bound/solution/ as a flat copy, with the full bystander fleet and the freeze ordering, and the tests/ conftest mirroring the root fixtures.
   - Replace the activity body with a CPU-bound transform of the provider response (the root cpu loop, recast); the bad run's input sets the work size.
   - Create solution/tests/test_probe.py: the 50 ms ticker probe asserting the cpu activity body on the executor does NOT starve the probe. Written to fail against the still-async computation on the loop.

2. Document component:
   - Module docstrings on solution activities.py and worker.py noting the 03-cpu-bound copy and the executor change.

3. GREEN: Convert the geo activities to def on the sync httpx client and pass activity_executor=ThreadPoolExecutor(...) in solution/worker.py, exactly as in Step 5; keep the CPU-bound transform body but with NO marker (it is correct on a pool thread); confirm `grep -rn "ANTIPATTERN" exercises/03-cpu-bound/solution` returns nothing.

4. Create exercises/03-cpu-bound/practice/: the SAME copy before the fix (async def geo activities, the GIL-pinning transform on the loop, carrying the busy-work antipattern marker), with `# TODO PART C:`/`# TODO PART D:` comments at the edit points and a practice/tests/test_probe.py stub.

5. Integrate into the gate: `just check` checks the new solution dir green; `just check-practice` passes for the new practice dir.

6. REFACTOR: Keep the solution-versus-practice diff limited to the fix lines and TODO comments.

7. Update documentation: none (README is Step 11).

8. Verify the probe test fails if the transform is moved back onto the loop, revert, then run `just check` and `just check-practice`.
```

### Step 8: Exercise 04 Zombie Thread

**NOTE**: Follows the template, but the practice copy starts from the fix most users ship first, and the solution is the correct shape.
The bug: get_location stays async def and wraps the blocker in asyncio.to_thread(...) under a heartbeat_timeout with no heartbeat. It looks right, which is why people ship it: the loop stays live, the bystanders are fine, and a starvation probe would pass.
The failure is that the activity runs twice. When the server times the attempt out, the coroutine is cancelled but the detached thread keeps running to completion; the retry then starts the same work beside it, so the Worker log shows the first thread finishing after its attempt already failed and the retry's work overlapping it (duplicate side effects, the thing an Activity must never do unnoticed), and `py-spy dump` shows the orphaned thread still inside the blocker after the failure.
The fix: a def activity on a ThreadPoolExecutor sized to max_concurrent_activities that heartbeats from its own thread (copy_context then heartbeat on an interval), so a timeout or cancel arrives as temporalio.exceptions.CancelledError inside the thread and the work stops.
Confirm the sync-heartbeat-from-a-thread pattern and the CancelledError-into-the-thread behavior against the temporal-docs MCP before writing the fix.
The two startup traps (a def activity with no activity_executor; an executor smaller than max_concurrent_activities) are captured in Step 10, not asserted here, except the Part D build_worker assertion below.

```text
1. RED: Create exercises/04-zombie-thread/solution/ as a flat copy, with the full bystander fleet, the freeze ordering, and the tests/ conftest mirroring the root fixtures.
   - Create solution/tests/test_cancel_stops_work.py: run the fixed def activity under temporalio.testing.ActivityEnvironment, start it, request cancel, and assert the work stops at the next heartbeat (a shared flag the activity sets on CancelledError shows the work did not run to completion after cancel). Add a second test that builds the worker via build_worker and asserts the activity_executor's _max_workers is >= max_concurrent_activities. Both written to fail against the to_thread-no-heartbeat practice shape and the unsized executor.

2. Document component:
   - Module docstrings on solution activities.py and worker.py noting the 04-zombie-thread copy: a def activity on a sized executor that heartbeats from its own thread, so cancellation reaches the work and no attempt's work outlives its attempt.

3. GREEN: In solution/activities.py, make get_ip and get_location def activities that do the blocking work and heartbeat from their own thread (guarded by activity.in_activity()), catching temporalio.exceptions.CancelledError to stop the work; in solution/worker.py pass activity_executor=ThreadPoolExecutor(max_workers=<max_concurrent_activities>); NO marker; confirm `grep -rn "ANTIPATTERN" exercises/04-zombie-thread/solution` returns nothing.

4. Create exercises/04-zombie-thread/practice/: the SAME copy in the shipped-first state (async def get_location wrapping the blocker in asyncio.to_thread under a heartbeat_timeout with no heartbeat, carrying the antipattern marker that explains why the cancel never reaches the thread, so the work finishes after the attempt failed and the retry runs it again), with `# TODO PART C:` at the to_thread line and the worker executor argument, and a practice/tests/test_cancel_stops_work.py stub carrying `# TODO PART D:`.

5. Integrate into the gate: `just check` checks the new solution dir green (including the cancel-stops-work and executor-size assertions); `just check-practice` passes for the new practice dir.

6. REFACTOR: Keep the solution-versus-practice diff to the activity body (to_thread to def-plus-heartbeat) and the worker executor argument and the TODO comments.

7. Update documentation: none (README is Step 11).

8. Verify the cancel test fails if the solution reverts to async def to_thread with no heartbeat, revert to the def-plus-heartbeat form, then run `just check` and `just check-practice`.
```

### Step 9: Exercise 05 Catching Blockers Early

**NOTE**: Follows the template.
This is the one detection exercise in the series and the only one allowed to misbehave without failing; keep it that way, and make it land.
The bug is a short synchronous serialization of a large payload inside an async def activity that stalls the loop a few hundred milliseconds on every run and never times out (decision: a pure-Python JSON round trip of a generated payload sized to take 200 to 500 ms on the capture machine; confirm at review).
The execution still misbehaves, and the reader must see that before the tool: every bystander dispatched into the stall waits it out, so the receipts, which complete in a few milliseconds in the healthy fleet, take a few hundred milliseconds on every run of this fleet, visible as the gap between the receipt activity's started and completed timestamps in `temporal workflow show` (Part A runs the healthy fleet and then this one and the reader compares the two).
Then the tool: Part B runs the Worker with asyncio debug mode (`PYTHONASYNCIODEBUG=1`) and captures the slow-callback warning that names the activity task, and `py-spy dump` confirms the serialization line.
The fix moves the work off the loop; the Part D test is the starvation probe parametrized over every registered async def activity, the regression guard that would have caught it in CI.
The lesson lands as: the blocker that has not taken anything down yet, the tool that catches it, and the test that keeps it out.

```text
1. RED: Create exercises/05-catching-blockers-early/solution/ as a flat copy, with the full bystander fleet, the freeze ordering, and the tests/ conftest mirroring the root fixtures.
   - In the practice-shaped source, get_location serializes a generated large payload synchronously (a pure-Python JSON round trip sized to a few hundred ms) inside async def; the starter's ordering submits the receipts while the serialization is running, so the receipt delay is reproducible on every run.
   - Create solution/tests/test_probe_all_activities.py: enumerate every async def activity registered on the worker and, for each, run its body under a 50 ms ticker probe (with network and payload inputs mocked), asserting none starves the probe. Written to fail against the still-on-loop serialization.

2. Document component:
   - Module docstring on solution activities.py noting the 05-catching-blockers-early copy and that the serialization runs off the loop, with the probe test as the regression guard.

3. GREEN: In solution/activities.py, move the serialization off the loop (await asyncio.to_thread(...) for the pure-Python work, or a def activity on the executor; choose the one that keeps the probe green and confirm against the temporal-docs MCP); NO marker; confirm `grep -rn "ANTIPATTERN" exercises/05-catching-blockers-early/solution` returns nothing.

4. Create exercises/05-catching-blockers-early/practice/: the SAME copy before the fix (the synchronous serialization on the loop, carrying the antipattern marker), with a `# TODO PART C:` comment at the serialization line and a practice/tests/test_probe_all_activities.py stub carrying `# TODO PART D:`.

5. Integrate into the gate: `just check` checks the new solution dir green (including the parametrized probe); `just check-practice` passes for the new practice dir.

6. REFACTOR: Keep the solution-versus-practice diff to the serialization line and the TODO comment.

7. Update documentation: none (README is Step 11).

8. Verify the parametrized probe fails if the serialization is moved back onto the loop, revert; then confirm `grep -rn "ANTIPATTERN (deliberate, for teaching)" exercises/*/solution` across ALL five exercises returns nothing, and run `just check` and `just check-practice`.
```

## Section 5: Live Captures

**Tools:** none

### Step 10: Capture Before And After For Every Exercise Plus The Baseline (task)

**NOTE**: Live and manual, so Task template, and it produces no committed code (captures land in the scratchpad and, for Grafana, under docs/images/).
This is where the dashboard metric names, the backlog panel, the second-Worker cpu demonstration, the slow-endpoint-in-the-starter decision, the metrics port 9465, and the asyncio debug-mode warning are confirmed against live output (the "confirm at review" decisions).
Every quoted block in the exercise READMEs and drafts must trace to a capture taken here, from that exercise's own copy.
Needs `temporal server start-dev` with `--metrics-port 9465`, the worker, the compose stack up, and ptrace_scope 0 for py-spy and asyncio ps.

```text
1. Scope:
   - Artifact(s): capture files in the session scratchpad (tool output, starter output, Worker log, temporal workflow show/describe output) and PNG screenshots under docs/images/ named <exercise>-<state>-<panel>.png; no src or exercise code changes except a possible dashboard-panel drop.
   - Desired end state: for the healthy baseline and for each of the five exercises in both the practice (before) and solution (after) states, a complete set of captures exists per spec Exercise requirements: asyncio ps / pstree, py-spy dump where a freeze is involved, CPU reading, the relevant metrics scrape or Grafana panel, the Worker log where the zombie or cancel is the point (02, 04), and the asyncio debug-mode warning (05). The backlog panel, the cpu second-Worker run, the slow endpoint served by the starter, and port 9465 are confirmed or corrected here.

2. Tooling:
   - Skills: temporal:temporal-developer
   - MCPs: mcp__temporal-docs__search_temporal_knowledge_sources (confirm exact metric names before quoting them)
   - External: temporal CLI (start-dev --metrics-port 9465), docker-compose v1 (just metrics), uvx py-spy, PYTHONASYNCIODEBUG for exercise 05, a browser or headless capture for Grafana PNGs

3. Do the work:
   - Start the stack: `just server` (confirm it binds 9465), `just metrics` (confirm Prometheus scrapes both 9464 and 9465 and Grafana serves on 3000 with the dashboard provisioned), `just worker`.
   - Baseline: run `just healthy` and capture the healthy asyncio ps shape, the activity-execution-latency panel at rest, and the workflow-task-latency panel.
   - Per exercise, run from the exercise's own directory with `uv run python worker.py` and `uv run python starter.py ...`:
     - 01 practice (before): the frozen-loop asyncio ps shape (one task dead-ended at _ActivityWorker._handle_start_activity_task), py-spy dump naming the httpx.Client call in get_location, CPU near zero, the cross-type rollup timeout, the workflow-task-latency spike on the dashboard. 01 solution (after): loop live, bystanders complete, py-spy shows the HTTP read on an executor thread, latency flat.
     - 02 practice (before): temporal workflow show listing attempt after attempt failing on Heartbeat timeout (the retry storm) through to the attempt that succeeds once the job is done, the Worker log still printing a dead attempt's poll lines after its failure (the zombie), bystanders failing in the frozen windows, py-spy naming the time.sleep line in the loop. 02 solution (after): temporal workflow describe shows the last heartbeat time advancing every second, the activity completes on its first attempt, bystanders normal.
     - 03 practice (before): frozen shape, top at about 100 percent on one core (capture it next to 01's near-zero reading; the README puts the pair side by side), py-spy in the compute loop, the rollup failure. 03 solution (after): loop live, py-spy shows the computation on an executor thread holding the GIL, top near 100 percent; also run a second Worker process and capture two cpu runs progressing with combined CPU above 100 percent.
     - 04 practice (before): bystanders fine, the first attempt times out, the Worker log shows the detached thread's work finishing after the failure and the retry's work overlapping it (the activity ran twice), py-spy dump showing the orphaned thread still inside the blocker after the attempt failed; capture the two startup traps (def activity with no activity_executor error; executor-smaller-than-max_concurrent_activities warning). 04 solution (after): the Worker log shows CancelledError in the thread and no work after it, no overlap.
     - 05 practice (before): every run completes, nothing times out; run the healthy fleet and then the practice fleet and capture the receipt activity's started-to-completed gap in temporal workflow show for each (milliseconds against a few hundred milliseconds); then asyncio debug mode's slow-step warning naming the activity task, and py-spy confirming the serialization line. 05 solution (after): the receipt gap back to milliseconds, no slow-step warning for the activity, the parametrized probe passes.
   - Save Grafana PNGs under docs/images/ as <exercise>-<state>-<panel>.png with the panel each exercise README will reference.
   - If the dev server does NOT export the Task Queue backlog gauge the dashboard assumes, drop that panel from observability/grafana/dashboards/async-debug.json, update tests/test_observability_config.py's allowlist accordingly, note it for the README, and re-run `just check`. Likewise correct any dashboard metric name that does not match the live /metrics output.

4. Verify:
   - Confirm every capture file needed by Steps 11 and 12 exists and is from the correct copy and state; confirm docs/images/ holds the baseline plus a before and after screenshot per exercise. Re-run `just check` if the backlog panel or any metric name was changed.

5. Document:
   - Keep a short scratchpad index mapping each capture file to the exercise, state, and tool, so Steps 11 and 12 can cite the source of every quoted block.
```

## Section 6: Exercise READMEs

**Tools:**
- Skills: content-design:tutorial-writing, voice:teaching, content-design:review-content, temporal:temporal-developer
- MCPs: mcp__temporal-docs__search_temporal_knowledge_sources
- Linters: just lint-prose exercises/*/README.md, just lint-keyboard exercises/*/README.md

### Step 11: Write The Five Exercise READMEs From The Captures (task)

**NOTE**: Prose from captures, so Task template.
Each README follows the 102 structure exactly and quotes only that exercise's own captures from Step 10.
Never invent output; if a capture is missing, flag it with CLAUDE_HELP and stop that README rather than fill the gap.
Writing hard rules apply: no em-dashes or en-dashes, straight quotes, sentence-case headings (Temporal education doc), one sentence per line.
Skill order for every prose step in this arc: invoke content-design:tutorial-writing first (it owns the structure, the code sandwich, and the mechanical canon), then voice:teaching (Mason's teaching register applied on top; it imports the tutorial-writing canon rather than re-deriving it, so where both are loaded the tutorial-writing rules win on mechanics), then draft, then content-design:review-content.
voice:teaching requires that every draft wait for Mason's eyes with a smell report attached and that nothing publishes autonomously.
In this loop the handoff is the commit on the scaffold branch, which only Mason merges, so that requirement is met by writing the smell report and the open questions for each artifact to docs/drafts/smell-reports.md (one H2 per artifact; one bullet per suspect item with the verbatim quote and the rule it may break; open questions inside CLAUDE_HELP tags) and committing that file with the prose.
Do not read the skill's wait-for-Mason rule as a reason to abort or to skip the step.
`just preflight` must exit 0 before drafting starts; a non-zero exit is a Failure for the step (fix Step 0's artifacts, never skip the gate).
The validator for this section consults voice:teaching in critique mode (findings only, each with the verbatim quote and the law behind it) and the tutorial-writing pre-submission checklist, runs the two declared linters, and maps Vale `error` to block, `warning` to warn, and `suggestion` to info; every keyboard-characters hit is a block.

```text
1. Scope:
   - Artifact(s): exercises/01-sync-http-client/README.md, exercises/02-sleep-between-heartbeats/README.md, exercises/03-cpu-bound/README.md, exercises/04-zombie-thread/README.md, exercises/05-catching-blockers-early/README.md, docs/drafts/smell-reports.md (new; one section per README)
   - Desired end state: five READMEs, each in the 102 structure: title "Exercise N: <Doing the thing>", "During this exercise, you will" bullets, the edit-practice / peek-at-solution note, a prerequisites section pointing at the root README setup and at `just metrics`, Parts A through E (run it and watch it misbehave; diagnose it with the Python tooling, `asyncio ps` / `pstree`, `py-spy dump`, the CPU reading, or asyncio debug mode, with the named Grafana panel as corroboration; find the bug; write the Part D test and fix it in practice; redeploy and verify), and the closing "### This is the end of the exercise." line. Each quotes only that exercise's captures and names the Grafana panel in the observe and verify parts.

2. Tooling:
   - Skills: content-design:tutorial-writing (invoke first), voice:teaching (invoke second, draft mode, teaching-refined register), content-design:review-content (invoke after drafting), temporal:temporal-developer
   - MCPs: mcp__temporal-docs__search_temporal_knowledge_sources (confirm any primitive name or metric name before it reaches prose)
   - External: `just preflight` (must pass first), Vale via review-content and `just lint-prose`, `just lint-keyboard`

3. Do the work:
   - Run `just preflight`; stop with a Failure on a non-zero exit.
   - Invoke content-design:tutorial-writing; follow its workflow (the output/ working files are gitignored under docs/drafts/output and are not these READMEs). Then invoke voice:teaching and read its profile in full before drafting.
   - For each exercise, write the README to exercises/<NN-name>/README.md using the Part A-E mapping: Part A runs the practice copy and the stack and shows the misbehavior as the reader would meet it in production (a failing bystander, a retry storm, the same work running twice, a slow receipt), framed as a problem to solve, not a lesson announced; Part B is the diagnosis the reader performs with the Python tooling, asyncio ps / pstree for the dead-ended task, py-spy where a freeze applies, the CPU reading for 03, the Worker log where the zombie or the overlap is the point, the asyncio debug-mode warning for 05, with the named Grafana panel last as the fleet-wide view of what the tooling found; Part C finds the bug at the TODO PART C line; Part D writes the Part D test (the one in practice/tests/) and applies the fix; Part E redeploys and verifies the after-state, quoting the solution capture and the same panel showing the fix.
   - Quote only captures from Step 10 for that exercise; match the after-states in spec Exercise requirements.
   - Keep every exercise framed as the one mechanism (a blocked event loop); do not drift into heartbeat, timeout, or retry tuning.
   - Point prerequisites at the root README setup and `just metrics`; do not restate the whole setup.
   - Write the smell report and open questions for each README to docs/drafts/smell-reports.md under an H2 named for the file.

4. Verify:
   - Invoke content-design:review-content on each README and address every finding (Vale MasonBase plus MasonTechnical, then the copy-editor pass).
   - `just lint-prose` shows no error-level Vale alert on any of the five READMEs; `just lint-keyboard` exits 0.
   - Human-check each README: 102 structure present, the closing line present, every quoted block traceable to a Step 10 capture of that exercise, the Grafana panel named, no em-dashes or en-dashes, sentence-case headings, one sentence per line; docs/drafts/smell-reports.md has a section per README.

5. Document:
   - This step is the documentation; the root README's Exercises table linking these is Step 13.
```

## Section 7: Tutorial Series Drafts

**Tools:**
- Skills: content-design:tutorial-writing, voice:teaching, content-design:review-content, temporal:temporal-developer, python:python
- MCPs: mcp__temporal-docs__search_temporal_knowledge_sources
- Linters: just lint-prose docs/drafts/part-*.md, just lint-keyboard docs/drafts/part-*.md

### Step 12: Write The Six-Part Series Drafts (task)

**NOTE**: Prose from the exercise READMEs and captures, so Task template.
Six drafts under docs/drafts/, written with the tutorial-writing skill, each Vale-clean and passed through review-content.
The tutorial-writing skill's own working files live under docs/drafts/output/ and are gitignored; the committed drafts are docs/drafts/part-N-*.md.
Drafts carry no frontmatter and use TODO placeholders for the previous and next links and the venue (the venue decision is deferred).
Skill order for every prose step in this arc: invoke content-design:tutorial-writing first (it owns the structure, the code sandwich, and the mechanical canon), then voice:teaching (Mason's teaching register applied on top; it imports the tutorial-writing canon rather than re-deriving it, so where both are loaded the tutorial-writing rules win on mechanics), then draft, then content-design:review-content.
voice:teaching requires that every draft wait for Mason's eyes with a smell report attached and that nothing publishes autonomously.
In this loop the handoff is the commit on the scaffold branch, which only Mason merges, so that requirement is met by writing the smell report and the open questions for each artifact to docs/drafts/smell-reports.md (one H2 per artifact; one bullet per suspect item with the verbatim quote and the rule it may break; open questions inside CLAUDE_HELP tags) and committing that file with the prose.
Do not read the skill's wait-for-Mason rule as a reason to abort or to skip the step.
`just preflight` must exit 0 before drafting starts; a non-zero exit is a Failure for the step (fix Step 0's artifacts, never skip the gate).
The validator for this section consults voice:teaching in critique mode (findings only, each with the verbatim quote and the law behind it) and the tutorial-writing pre-submission checklist, runs the two declared linters, and maps Vale `error` to block, `warning` to warn, and `suggestion` to info; every keyboard-characters hit is a block.

```text
1. Scope:
   - Artifact(s): docs/drafts/part-1-healthy-worker.md, part-2-sync-http-client.md, part-3-sleep-between-heartbeats.md, part-4-cpu-bound.md, part-5-zombie-thread.md, part-6-catching-blockers-early.md, docs/drafts/smell-reports.md (one section per part, appended)
   - Desired end state: six drafts in the tutorial-writing structure (Title H1, Introduction H3, Prerequisites H2, "Step N: Gerund phrase" H2, Conclusion H2; sentence case; second person; code sandwich; Temporal primitives capitalized), each linking the previous and next parts with TODO placeholders and carrying no frontmatter. Part 1 covers install, ptrace_scope, `just server`, `just worker`, `just metrics`, `just healthy`, and the baseline readings including the dashboard. Parts 2 to 6 follow exercises 01 to 05 and end with the reader's fix and its verification. The series title is "Debugging blocking calls in Temporal async Activities".

2. Tooling:
   - Skills: content-design:tutorial-writing (invoke first; its outline step writes docs/drafts/output/outline.md, gitignored and generated fresh from the new captures), voice:teaching (invoke second, draft mode, teaching-refined register), content-design:review-content (invoke after drafting), temporal:temporal-developer, python:python
   - MCPs: mcp__temporal-docs__search_temporal_knowledge_sources (confirm primitive and metric names before prose)
   - External: `just preflight` (must pass first), Vale via review-content and `just lint-prose`, `just lint-keyboard`, the wordcount tool bundled with the tutorial-writing skill

3. Do the work:
   - Run `just preflight`; stop with a Failure on a non-zero exit.
   - Invoke content-design:tutorial-writing; generate the outline from the Step 10 captures and the exercise READMEs; get the structure right for six parts before writing sections. Then invoke voice:teaching and read its profile in full before drafting.
   - Write part 1 from the baseline captures and the root README setup; write parts 2 to 6 from exercises 01 to 05's READMEs and captures, each ending with the reader changing code in practice/ and re-running the recipe to see the failure gone.
   - Quote only captures from Step 10; never generate code or output; flag any gap with CLAUDE_HELP and continue.
   - Keep the whole series on the one mechanism; do not add a heartbeat, timeout, or retry-policy part.
   - Use TODO placeholders for previous/next links and the venue; add no frontmatter.
   - Append the smell report and open questions for each part to docs/drafts/smell-reports.md under an H2 named for the file.

4. Verify:
   - Run Vale (via review-content) on each draft and fix until clean (MasonBase plus MasonTechnical); run the copy-editor pass; track length with the wordcount tool.
   - `just lint-prose` shows no error-level Vale alert on any of the six drafts; `just lint-keyboard` exits 0.
   - Human-check: six drafts present, no frontmatter, the series title correct, every quoted block traceable to a Step 10 capture, no em-dashes or en-dashes, sentence-case headings, one sentence per line, Temporal primitives capitalized; docs/drafts/smell-reports.md has a section per part.

5. Document:
   - docs/drafts/README.md is updated in Step 13 to list these six drafts.
```

## Section 8: Root Documentation Refresh

**Tools:**
- Skills: content-design:tutorial-writing, voice:teaching, content-design:review-content
- MCPs: none
- Linters: just lint-prose README.md CLAUDE.md docs/drafts/README.md, just lint-keyboard README.md CLAUDE.md docs/drafts/README.md

### Step 13: Root README, CLAUDE.md, And docs/drafts/README Refresh (task)

**NOTE**: Prose and layout refresh, so Task template, and the last step.
The root README drops to three lessons (healthy, blocking call, CPU bound), all recaptured from the trimmed package in Step 10, and gains the Exercises table and Observability section.
CLAUDE.md is refreshed to the trimmed package, the three-layer layout, and the solution-copy carve-out.
docs/drafts/README.md lists the six drafts and the smell-reports file.
Writing hard rules apply throughout.
Skill order for every prose step in this arc: invoke content-design:tutorial-writing first (it owns the structure, the code sandwich, and the mechanical canon), then voice:teaching (Mason's teaching register applied on top; it imports the tutorial-writing canon rather than re-deriving it, so where both are loaded the tutorial-writing rules win on mechanics), then draft, then content-design:review-content.
voice:teaching requires that every draft wait for Mason's eyes with a smell report attached and that nothing publishes autonomously.
In this loop the handoff is the commit on the scaffold branch, which only Mason merges, so that requirement is met by writing the smell report and the open questions for each artifact to docs/drafts/smell-reports.md (one H2 per artifact; one bullet per suspect item with the verbatim quote and the rule it may break; open questions inside CLAUDE_HELP tags) and committing that file with the prose.
Do not read the skill's wait-for-Mason rule as a reason to abort or to skip the step.
`just preflight` must exit 0 before drafting starts; a non-zero exit is a Failure for the step (fix Step 0's artifacts, never skip the gate).
The validator for this section consults voice:teaching in critique mode (findings only, each with the verbatim quote and the law behind it) and the tutorial-writing pre-submission checklist, runs the two declared linters, and maps Vale `error` to block, `warning` to warn, and `suggestion` to info; every keyboard-characters hit is a block.

```text
1. Scope:
   - Artifact(s): README.md (edit), CLAUDE.md (edit), docs/drafts/README.md (edit), docs/drafts/smell-reports.md (append a section for README.md)
   - Desired end state:
     - README.md has exactly three lessons (healthy, frozen loop from a blocking call, frozen loop from CPU-bound code), their output blocks recaptured from the trimmed package; lessons 4 to 7, "Which timeout fires, and how to tell", and the timeout-tuning parts of "Realistic timeouts" are removed. README gains an "Exercises" table in the 102 root-README shape (directory, exercise link) linking each exercises/<NN-name>/README.md, and an "Observability" section stating what `just metrics` starts, where the dashboard is (localhost:3000), the dev server metrics port 9465 and why `just server` sets it, and (if the backlog panel was dropped in Step 10) that the dev server does not export the backlog gauge. The series title with a TODO link is present.
     - CLAUDE.md describes the trimmed package (block and cpu only), the three-layer layout (root reference, exercises, observability), the solution-copy carve-out (a solution/ copy carries no antipattern and no marker; grep excludes it), the new `just` recipes (server --metrics-port 9465, metrics, metrics-down, check solution loop, check-practice, preflight, lint-prose, lint-keyboard), and the per-directory gate; it keeps the antipattern marker convention section.
     - docs/drafts/README.md lists the six drafts and docs/drafts/smell-reports.md (what it is, who reads it), keeps the provenance note on the original draft, and keeps the venue as not yet chosen.

2. Tooling:
   - Skills: content-design:tutorial-writing (invoke first), voice:teaching (invoke second, edit mode on the README's prose), content-design:review-content (run on README.md after editing)
   - MCPs: none
   - External: `just preflight` (must pass first), Vale via review-content and `just lint-prose`, `just lint-keyboard`

3. Do the work:
   - Run `just preflight`; stop with a Failure on a non-zero exit. Invoke content-design:tutorial-writing, then voice:teaching, before touching README.md.
   - Rewrite the root README to three lessons with the recaptured blocks; remove the saturation, heartbeat, schedule-to-start, and timeout-tuning sections; add the Exercises table, the Observability section, the series title, and a TODO tutorial link; list preflight, lint-prose, and lint-keyboard in the recipe table.
   - Rewrite CLAUDE.md's architecture and commands to the trimmed package, the three-layer layout, the solution-copy carve-out, and the new recipes; keep the antipattern marker convention section and confirm its grep string, extending it to note the solution-copy exclusion; remove references to the removed modes, the quote, and the saturation recipes.
   - Update docs/drafts/README.md to list part-1 through part-6 and smell-reports.md, keep the original-draft provenance note, and keep the venue note.
   - Append the README.md smell report and open questions to docs/drafts/smell-reports.md.
   - Apply the writing hard rules: no em-dashes or en-dashes, straight quotes, one sentence per line in committed Markdown, sentence-case headings.

4. Verify:
   - Run content-design:review-content on README.md and address findings; `just lint-prose` shows no error-level Vale alert on README.md, CLAUDE.md, or docs/drafts/README.md; `just lint-keyboard` exits 0.
   - Grep CLAUDE.md and README.md for stale references (removed modes, the quote, saturation, maximum_attempts); confirm the module and layer list matches the tree (`ls exercises/`, `ls observability/`); confirm `grep -rn "ANTIPATTERN (deliberate, for teaching)" exercises/*/solution` returns nothing; run `just check` and `just check-practice` and confirm exit 0.

5. Document:
   - This step is the documentation.
```

## Section 9: Post-Review Rework (Mason's rulings, 2026-11-05)

**Tools:**
- Skills: python:python, temporal:temporal-developer
- MCPs: mcp__temporal-docs__search_temporal_knowledge_sources
- Linters: uv run ruff check --output-format=json ., uv run mypy .

Mason reviewed the finished arc on 2026-11-05 and ruled on every open item.
The rulings, which win over anything earlier in this plan:

- Exercise 02 is rebuilt so the reader sees a visible retry storm. A scratch spike (scratchpad `spike02/`, logs `spike-worker.log` and `spike-starter.log`) proved the design: an awaited status check before each poll, the blocking `time.sleep(8)` kept, and `JOB_SECONDS` raised from 20 to 60. In the spike the bad run's Attempt counter climbed 1 to 4 in `temporal workflow describe`, every attempt failed with a Heartbeat timeout, cancels landed late (attempts 1 and 2 kept polling as overlapping zombies), the rollup failed, receipts stalled, two `TMPRL1101` deadlock errors appeared in the Worker log, and the run completed after about 65 s.
- Temporal writes no history event per retried Activity attempt, so `temporal workflow show` never lists attempt after attempt. The storm is shown in the Temporal Web UI's pending-activity view (attempt count and last failure), in `temporal workflow describe`, in the Worker log, and in the Grafana `activity_timeout` panel. Web UI screenshots are allowed for exercise 02.
- The exercise 02 README calls out `TMPRL1101 Potential deadlock detected` as a frozen-loop clue: on an `async def` Worker it can mean the event loop is blocked, not that the Workflow code deadlocked.
- Draft part 3 keeps leaving out the 4 s server-side heartbeat cadence.
- Exercise 05 keeps `zlib.compress`, because it releases the GIL and so the `asyncio.to_thread` fix visibly restores receipt latency (a pure-Python JSON blocker kept receipts slow after the fix through GIL contention). The `os.urandom` stand-in bytes become generated, realistic audit-log lines built inside the Worker. Nothing binary crosses a Temporal boundary: `get_location(ip: str, payload_records: int) -> str` stays as is. The README adds that a real archiver uploads the compressed bytes to blob storage and returns a key, never the blob.
- A small receipt-gap helper is committed so readers can reproduce every gap figure. The full capture script stays deferred.
- Exercise 03 ships a metrics-port setting so the second-Worker extension runs from the repository.
- Exercise 04's forced-timeout demo stays a described extension (the reader edits `STEP_SECONDS` to 6.0 themselves). No repository change.
- The root README gets quoted `temporal workflow show` histories for the rollup and a receipt under `just block`.
- Draft part 1 gets a captured py-spy ptrace failure and the `sysctl` fix. Changing `kernel.yama.ptrace_scope` needs sudo with a password, so Mason captures it by hand before the loop starts (see Step 19), and the files land in the scratchpad at `captures/root-ptrace/`.
- `.vale.ini` turns off `MasonBase.Headings` under `exercises/**` and `docs/drafts/**`.
- The backlog framing stays: `temporal task-queue describe` is the reliable reading, and the dashboard corroborates.

Captures from Step 10 still stand for everything these rulings do not touch, and the scratchpad `captures/INDEX.md` and `captures/FINDINGS.md` stay the source of truth for them.
New captures land in the same scratchpad tree and get INDEX rows.

### Step 14: Reconcile spec.md, plan.md, And .vale.ini With The Rulings (task)

**Tools:**
- Skills: none
- MCPs: none
- Linters: just lint-prose spec.md, just lint-keyboard spec.md plan.md .vale.ini

```text
1. Scope:
   - Artifact(s): spec.md, plan.md (the header fence paragraph, the Architecture Recap table rows for 02 and 05, and the Implementation Guidelines bullets that name the deferred items and the confirm-at-review list), .vale.ini
   - Desired end state: spec.md reads as current intent on one pass, with every ruling above applied in place and no stale prediction left; plan.md's earlier text no longer forbids what Section 9 does; Vale stops flagging sentence-case headings under exercises/ and docs/drafts/.

2. Tooling:
   - Skills: none
   - MCPs: none
   - External: just lint-prose, just lint-keyboard, vale ls-config

3. Do the work:
   - spec.md, exercise 02: rewrite the bullet to the spiked design (an awaited async status check before each poll, then the blocking time.sleep of the poll interval; heartbeat_timeout 5 s, poll 8 s, job 60 s keyed on the run id). State the observed shape: the Attempt counter climbs in describe and the Web UI, every attempt fails on Heartbeat timeout, cancels land late so failed attempts keep polling as zombies, bystanders fail and stall, TMPRL1101 deadlock warnings appear, and workflow show writes no per-attempt event. Keep the awaited 1-second tick fix. Drop "(confirm at review)".
   - spec.md, exercise 05: the blocker is one zlib.compress at level 9 over generated audit-log lines built in the Worker (about 350 ms), with the GIL reason in one sentence. The symptom is the receipts' first Workflow Task gap. The asyncio debug warning names the SDK handler `_ActivityWorker._handle_start_activity_task`, so py-spy names the line. Add the blob-storage-key note as a README requirement.
   - spec.md, exercise 03: the second-Worker extension runs from the repo through a metrics-port setting (an environment variable read by worker.py in both copies, default 9464).
   - spec.md, Deferred list: move "Temporal Web UI screenshots" out of Deferred into the exercise 02 requirements (exercise 02 only). Narrow the "committed capture script" entry: a receipt-gap helper at scripts/receipt_gaps.py ships now; a script that reproduces whole runs stays deferred.
   - spec.md, Invariants: add spec.md, todo.md, plan.md, .ai-sessions/**, scripts/** to the paths: line.
   - spec.md: resolve every remaining "(confirm at review)" that the Step 10 captures confirmed (max_concurrent_activities=2, port 9465, the slow endpoint served by the starter, the per-directory gate loop, the second-Worker demo), rewriting each as a plain decided requirement. Fix the exercise 02 "last heartbeat advancing every second" wording to the observed about-every-4-seconds cadence.
   - plan.md: update the header paragraph and Implementation Guidelines so they no longer list "no committed capture script, no Web UI screenshots" without the Section 9 exceptions; update the 02 and 05 rows of the Architecture Recap table and the confirm-at-review bullet to match spec.md. Do not touch Sections 0 to 8's step bodies (they are history).
   - .vale.ini: add `MasonBase.Headings = NO` under the exercises and docs/drafts section(s). Keep every other rule.
   - Writing hard rules: one sentence per line, no em or en dashes, straight quotes.

4. Verify:
   - `grep -n "confirm at review\|retry storm\|attempt after attempt\|JSON round trip\|os.urandom" spec.md` returns nothing that contradicts the rulings.
   - `vale ls-config` shows MasonBase.Headings off for exercises/ and docs/drafts/ files; `just lint-prose spec.md` shows no error-level alert; `just lint-keyboard spec.md plan.md` exits 0; `uv run pytest -q` exits 0.

5. Document:
   - none beyond the edits (CLAUDE.md is Step 22).
```

### Step 15: Commit The Receipt-Gap Helper

**NOTE**: The scratchpad `gaps.py` produced every quoted receipt-gap figure; this step turns its two definitions into a small, tested, committed script.
Definitions to keep exactly: "WT1" is the first WorkflowTaskStarted to the first WorkflowTaskCompleted (it spans a WorkflowTaskTimedOut and its retry, which is the stall), and each Activity reports scheduled-to-started and started-to-completed in milliseconds.
The script reads `temporal workflow show -w <id> --output json` (stdlib only: json, subprocess, argparse, datetime), takes Workflow IDs or a `--limit N` listing filtered to OrderReceiptWorkflow, and prints one line per Workflow in the gaps.py format.

```text
1. RED: Write tests first:
   - Create tests/fixtures/ with two captured history JSON files copied from the scratchpad captures (one receipt whose first Workflow Task timed out and retried, one healthy receipt). If no receipt history JSON was saved in Step 10, capture one of each now from a root `just block` run and a `just healthy` run and record them in INDEX.md.
   - Create tests/test_receipt_gaps.py:
     - Test that the WT1 gap for the timed-out receipt spans the timeout and retry (first Started to first Completed), matching a value computed by hand from the fixture timestamps.
     - Test that a healthy receipt's WT1 gap and Activity gaps match hand-computed values.
     - Test that a history with no Activity still prints the WT1 gap and the total.
     - Test that the --limit listing keeps only OrderReceiptWorkflow entries (feed a fake listing through an injected runner, never a live server).

2. Document component:
   - Module docstring on scripts/receipt_gaps.py: what WT1 means, why it can span a timed-out Workflow Task, and the exact command a reader runs from any exercise directory.

3. GREEN: Create scripts/receipt_gaps.py with the minimal code to pass; keep the subprocess call behind one small function the tests replace. Full type hints, Google-style docstrings, no single-letter names.

4. RED: Add a parity test: running the script's formatter over every receipt history JSON in tests/fixtures/ reproduces the matching line in the scratchpad receipt-gaps capture for that Workflow, when one exists.

5. GREEN: Wire it up: add a `receipt-gaps *args` recipe to the justfile that runs `uv run python scripts/receipt_gaps.py {{args}}` from the repo root; make sure root ruff, ruff format --check, and mypy cover scripts/ and tests cover it under `just check`.

6. REFACTOR: Keep the script under about 100 lines with one formatting path shared by the ID and --limit modes.

7. Update documentation: none here (READMEs and drafts point at it in Steps 20 to 22).

8. Verify the tests fail if WT1 is changed to the last Workflow Task, revert, then run `just check`.
```

### Step 16: Exercise 03 Metrics-Port Setting

**NOTE**: The second-Worker extension collided on 127.0.0.1:9464. Both exercise 03 copies read the Prometheus port from an environment variable (name it `ASYNC_DEBUG_METRICS_PORT`, default 9464), so a second Worker starts with `ASYNC_DEBUG_METRICS_PORT=9466 uv run python worker.py`.
The setting is not part of the fix, so the practice-versus-solution diff does not change. The startup banner prints the port it bound.

```text
1. RED: In exercises/03-cpu-bound/solution/tests/, add tests for the port resolution: unset gives 9464; a valid integer overrides it; an empty, non-integer, or out-of-range value raises a ValueError that names the variable.

2. Document component: docstring on the port-resolution function and one line in the worker banner text.

3. GREEN: Implement the resolution in exercises/03-cpu-bound/solution/worker.py and use it where the Runtime's Prometheus address is built; mirror the same change into exercises/03-cpu-bound/practice/worker.py (and its tests, so the practice copy stays type-clean under check-practice).

4. RED: Add a test that build_worker (or the runtime builder) receives the resolved address string, using the copy's existing test seams.

5. GREEN: Wire it up minimally.

6. REFACTOR: Keep the diff between the two copies limited to the original fix lines and TODO comments.

7. Update documentation: none (README in Step 20).

8. Verify: `just check` and `just check-practice` exit 0; two Workers start side by side from the solution directory with different ports (a short live smoke run against the dev server, not a test).
```

### Step 17: Rebuild Exercise 02 For A Visible Retry Storm

**NOTE**: Apply the spiked design to both copies. The practice copy keeps its antipattern marker, rewritten so it stays true: the heartbeat cannot leave while time.sleep holds the loop, the server fails the attempt on Heartbeat timeout, and the cancel only lands at the next await, after the blocking sleep, so failed attempts keep polling as zombies and the retries freeze the loop again.
The awaited status check is a small `async def` in activities.py that stands in for an asynchronous status call (it awaits briefly, never touches the network), so tests stay offline.
`JOB_SECONDS` becomes 60.0. The heartbeat_timeout (5 s), the poll interval (8 s), and the Workflow's timeouts stay fixed scenery; confirm the 150 s schedule_to_close still covers a 60 s job plus the storm in the solution and practice runs.
The solution keeps the awaited 1-second tick wait with a heartbeat per tick, plus the same awaited status check.

```text
1. RED: Update exercises/02-sleep-between-heartbeats/solution/tests/: keep the heartbeat-count-and-probe test working with the new status check and job length (shrink the job in the test through the existing seams; never wait 60 s in a test); add a test that the awaited status check observes the same job across attempts (keyed on the run id).

2. Document component: update the module docstrings in both copies' activities.py to the new shape (awaited status check, 60 s job).

3. GREEN: Apply the change to solution/activities.py (status check awaited before each poll, JOB_SECONDS 60.0, tick wait unchanged; no marker) and confirm `grep -rn "ANTIPATTERN" exercises/02-sleep-between-heartbeats/solution` is empty.

4. Update the practice copy the same way, keeping time.sleep(POLL_INTERVAL_SECONDS), the rewritten marker, the `# TODO PART C:` comment, and the Part D stub.

5. Integrate into the gate: `just check` green for the solution, `just check-practice` green for the practice copy.

6. REFACTOR: The practice-versus-solution diff stays the wait (one sleep line versus the tick loop) plus the TODO comment.

7. Update documentation: none (README in Step 20).

8. Verify the solution test fails if the tick loop is reverted to the single time.sleep, revert, then run `just check` and `just check-practice`. Then run the practice fleet once against the dev server and confirm the Attempt counter climbs past 2 in `temporal workflow describe` (a smoke check; the captures are Step 19).
```

### Step 18: Exercise 05 Realistic Audit Trail

**NOTE**: Replace the `os.urandom` stand-in with generated audit-log lines: deterministic (seeded `random.Random`), plain JSON lines with realistic fields (timestamp, request id, client ip, action, status, latency in ms), built once at import and cached as encoded bytes, so the per-call cost is still only the compression.
Size the trail so one `zlib.compress(..., 9)` takes about 300 to 400 ms on this machine (measure with a short timing loop and record the result in the INDEX); adjust `PAYLOAD_RECORDS` and the record shape, not the compression level, and keep `RECORD_BYTES` only if it still means something.
The trail never crosses a Temporal boundary. The Activity signature and return value stay `get_location(ip: str, payload_records: int) -> str`.
The solution keeps `archived = await asyncio.to_thread(_archive_audit_trail, ip, payload_records)`.

```text
1. RED: In exercises/05-catching-blockers-early/solution/tests/, add tests for our generator: every line parses as JSON with the expected fields; the line count equals the requested records; the same seed gives the same bytes; the trail is compressible (compressed length well under the raw length). Keep the parametrized probe test.

2. Document component: rewrite the docstrings on the trail builder and _archive_audit_trail (realistic lines, built in the Worker, discarded after compressing; a real archiver would upload the bytes and return a key), and the PAYLOAD_RECORDS docstring in shared.py.

3. GREEN: Implement the generator in solution/activities.py; remove the os import if unused.

4. Mirror the change into the practice copy, keeping its antipattern marker, its TODO comments, and the direct call on the loop.

5. Integrate: `just check` and `just check-practice` exit 0.

6. REFACTOR: Keep the practice-versus-solution diff to the to_thread line and the TODO comment.

7. Update documentation: none (README in Step 20).

8. Verify the probe test fails if the solution's to_thread is reverted to the direct call, revert, then run `just check`. Record the measured compress time.
```

### Step 19: Recapture For The Rework (task)

**Tools:** none

**NOTE**: Live and manual, like Step 10. Use the dev server WITH its Web UI (`just server`, UI on 127.0.0.1:8233) for the exercise 02 screenshots, the compose stack (`just metrics`), and the scratchpad `shot.py` pattern (Playwright via `uv run --with playwright`) for both Grafana panels and the Web UI.
The ptrace capture needs sudo with a password, so Mason takes it by hand before the loop starts and saves it to the scratchpad at `captures/root-ptrace/` (py-spy failing with ptrace_scope 1, then the `sysctl` command restoring 0). If those files are missing, record a CLAUDE_HELP in the INDEX and continue; never attempt sudo.

```text
1. Scope:
   - Artifact(s): scratchpad captures (captures/02-practice-v2/, 02-solution-v2/, 05-practice-v2/, 05-solution-v2/, root-block-histories/, 03-solution-second-worker/), INDEX.md rows for each, a FINDINGS.md section "Rework captures (2026-11-05)", PNGs under docs/images/ (02 Web UI pending-activity screenshots named 02-practice-ui-<view>.png, and replacement 02 and 05 Grafana PNGs).
   - Desired end state: every claim Steps 20 to 22 make has a capture behind it.

2. Tooling:
   - Skills: temporal:temporal-developer
   - MCPs: mcp__temporal-docs__search_temporal_knowledge_sources
   - External: temporal CLI, docker-compose v1, uvx py-spy, PYTHONASYNCIODEBUG, Playwright through uv run --with, scripts/receipt_gaps.py

3. Do the work:
   - 02 practice: starter output; `temporal workflow describe` of the bad run sampled every 8 s (attempt and last failure); Web UI screenshots of the bad run's pending activity at two attempt counts; the Worker log with the zombie poll lines and the TMPRL1101 lines; `temporal workflow show` text (to show it lists no per-attempt failure) and its JSON; asyncio ps and py-spy dump during a freeze; receipt gaps via scripts/receipt_gaps.py; Grafana PNGs including activity_timeout.
   - 02 solution: first-attempt completion, describe heartbeat reads, receipt gaps, Grafana PNGs.
   - 05 practice and solution: healthy-vs-practice receipt gaps via scripts/receipt_gaps.py, the asyncio debug warning, py-spy naming the zlib.compress line, the measured compress time, solution gaps with and without debug mode, Grafana PNGs.
   - Root: `just block` with `temporal workflow show` for the failed rollup and one receipt (text and JSON), plus receipt gaps.
   - 03 solution: two Workers started with different ASYNC_DEBUG_METRICS_PORT values, two cpu runs progressing, top showing combined CPU above 100 percent.
   - Copy any receipt history JSON the Step 15 fixtures need.

4. Verify:
   - Every artifact above exists with an INDEX row naming exercise, state, tool, command, and time; FINDINGS records any new contradiction; `just check` still exits 0 if a fixture or dashboard changed.

5. Document:
   - INDEX.md rows and the FINDINGS section.
```

## Section 10: Rework Prose

**Tools:**
- Skills: content-design:tutorial-writing, voice:teaching, content-design:review-content, temporal:temporal-developer
- MCPs: mcp__temporal-docs__search_temporal_knowledge_sources
- Linters: just lint-prose exercises/*/README.md docs/drafts/part-*.md README.md CLAUDE.md, just lint-keyboard exercises/*/README.md docs/drafts/part-*.md README.md CLAUDE.md

The Section 6 to 8 rules carry over unchanged: `just preflight` first, tutorial-writing then voice:teaching then review-content, every quoted block a mechanical splice of a capture through the scratchpad build scripts (`build_readmes.py`, `build_drafts.py`, `build_readme.py` and their sources), every trim disclosed in one active sentence, and smell reports plus CLAUDE_HELP questions in docs/drafts/smell-reports.md.
Mark each smell-report item these steps settle as Resolved, citing the ruling.

### Step 20: Update The Exercise READMEs (task)

```text
1. Scope:
   - Artifact(s): exercises/02-sleep-between-heartbeats/README.md (Parts A, B, C, E rewritten), exercises/05-catching-blockers-early/README.md, exercises/01-sync-http-client/README.md and exercises/03-cpu-bound/README.md (Part D wording; 03 second-Worker section), exercises/04-zombie-thread/README.md (trap 1 disclosure), every receipt-gap block in all five READMEs, docs/drafts/smell-reports.md.
   - Desired end state: each README matches its rebuilt code and the Step 19 captures.

2. Tooling: as the section's Tools block, plus `just preflight`.

3. Do the work:
   - 02: Part A shows the storm through the Web UI screenshots, the climbing Attempt in describe, the failing rollup, and stalled receipts; say plainly that workflow show writes no event per retried attempt. Part B adds the TMPRL1101 callout as a frozen-loop clue next to asyncio ps and py-spy, with the Grafana activity_timeout panel last. Part E quotes the solution captures.
   - 05: describe the trail as generated audit-log lines, add the upload-and-return-a-key sentence, and replace every number and quoted block with the Step 19 captures.
   - 01 and 03 Part D: the hinted test fails first at `assert isinstance(executor, ThreadPoolExecutor)` because practice build_worker passes no activity_executor; a probe over the async def fails on a gap the length of the wait.
   - 03: the second-Worker section uses `ASYNC_DEBUG_METRICS_PORT=9466 uv run python worker.py` and the Step 19 capture; drop the scratch-copy disclosure.
   - 04: fix "This is the last line of the error from the capture." to match the four-line block.
   - All five: each receipt-gap block names the command `just receipt-gaps <workflow-ids>` (or `uv run python ../../scripts/receipt_gaps.py`) that produced it.
   - Update the smell reports.

4. Verify: review-content on each changed README; `just lint-prose` no error-level alert; `just lint-keyboard` exits 0; the build scripts reproduce each README byte for byte from its sources.

5. Document: smell-reports.md updated.
```

### Step 21: Update The Series Drafts (task)

```text
1. Scope:
   - Artifact(s): docs/drafts/part-1-healthy-worker.md (clone URL from `git remote get-url origin`, the ptrace capture if Mason saved it), part-3-sleep-between-heartbeats.md (rebuilt 02, TMPRL1101 callout, Web UI screenshots; keep the 4 s cadence cut), part-4-cpu-bound.md (Step 10 second Worker through ASYNC_DEBUG_METRICS_PORT), part-6-catching-blockers-early.md (new 05 trail and numbers, the key note), the receipt-gap blocks in parts 2, 3, 4, and 6, docs/drafts/smell-reports.md.
   - Desired end state: the drafts match the READMEs and the Step 19 captures.

2. Tooling: as the section's Tools block, plus `just preflight` and wordcount.

3. Do the work: apply the same changes as Step 20 to the drafts; resolve the matching CLAUDE_HELP blocks in the drafts and smell reports (receipt-gap helper, second Worker, part 1 clone URL and ptrace if captured, part 6 workflow show).

4. Verify: review-content on each changed draft; `just lint-prose` no error-level alert; `just lint-keyboard` exits 0; build_drafts.py reproduces each draft byte for byte.

5. Document: smell-reports.md updated.
```

### Step 22: Update The Root README And CLAUDE.md (task)

```text
1. Scope:
   - Artifact(s): README.md (quoted rollup and receipt histories from root-block-histories, the receipt-gaps recipe, scripts/ in the recipe table), CLAUDE.md (scripts/ layer, receipt-gaps recipe, 02 and 05 facts from the rework captures, exercise 03 port setting, Vale Headings scoping), docs/drafts/smell-reports.md (README section).
   - Desired end state: the root docs describe the repository as it now stands.

2. Tooling: as the section's Tools block, plus `just preflight`.

3. Do the work: splice the root histories through build_readme.py with disclosed trims, replacing the pointer to exercise 01; resolve the README CLAUDE_HELP about a later root capture pass; update CLAUDE.md's Layout, Commands, Architecture, and dashboard-fact bullets; update the README smell report.

4. Verify: review-content on README.md; `just lint-prose README.md CLAUDE.md` no error-level alert; `just lint-keyboard` exits 0; `just check` and `just check-practice` exit 0; `grep -rn "ANTIPATTERN (deliberate, for teaching)" exercises/*/solution` returns nothing.

5. Document: this step is the documentation.
```

## Implementation Guidelines

- One mechanism only. Every lesson, exercise, capture, README, and draft is about blocking the shared asyncio event loop. No step may add a slot-exhaustion, Worker-sizing-for-throughput, heartbeat-tuning, timeout-tuning, schedule-to-start, or retry-policy lesson, even as a contrast case. Heartbeats and timeouts appear only as fixed scenery or as symptoms of a frozen loop, never as the subject the reader tunes.
- Every exercise's bug is an execution failure the reader sees without a dashboard (bystanders fail, attempts fail and retry, the same work runs twice, a bystander is visibly delayed on every run), diagnosed with the Python tooling the reader runs (`asyncio ps`, `pstree`, `py-spy dump`, the CPU reading, asyncio debug mode). A metrics blip alone is not a bug, and Grafana corroborates rather than teaches. Exercise 05 is the one detection lesson and the only exercise that misbehaves without failing; do not add a second.
- All Python code follows the python:python skill without exception: full type hints, Google-style docstrings on public interfaces, no single-letter names, canonical ruff/mypy/pytest config blocks verbatim, PEP 604 X | None, absolute (flat top-level) imports in the exercise copies rather than relative imports.
- The root package is trimmed in Step 1 and then frozen for the rest of the arc; after Step 1 every code change lands under exercises/ or observability/. The invariant paths are src/temporal_async_debug/**, tests/**, exercises/**, observability/**, docs/**, justfile, pyproject.toml, README.md, CLAUDE.md, .vale.ini, .github/workflows/ci.yml, spec.md, todo.md, plan.md, .ai-sessions/**, scripts/**.
- No new Python runtime dependency. The fixes use the standard library (concurrent.futures.ThreadPoolExecutor, asyncio, time, http.server, json, contextvars, threading) and the httpx already present (its synchronous Client stands in for requests); py-spy stays uvx; Prometheus and Grafana run in containers. A dev-group parser for the config tests is acceptable only if one is already in the dependency group.
- The Temporal server is always `temporal server start-dev` with `--metrics-port 9465`; never a cluster, a server container, or Cloud. The compose stack is Prometheus and Grafana only and stays docker-compose v1 compatible; a test asserts no service image names Temporal.
- 102 layout: exercises/<NN-name>/{README.md,practice/,solution/}; each copy is a standalone flat set of modules plus tests/, runs from its own directory under the root virtual environment, and the practice edit points carry `# TODO PART X:` comments. A practice/ copy keeps the antipattern and its marker; a solution/ copy carries no antipattern and no marker. `grep -rn "ANTIPATTERN (deliberate, for teaching)" exercises/*/solution` must return nothing.
- Every quoted block in an exercise README or a draft is a capture of that exercise's own copy (or of the root package for the root README and part 1), taken live in Step 10. No reconstructed output; flag a missing capture with CLAUDE_HELP rather than invent it.
- Tests never require a running Temporal server except through the SDK's own facilities (ActivityEnvironment, WorkflowEnvironment.start_time_skipping()); all network is mocked, and exercise 01 serves its slow endpoint from a stdlib server inside the test. Guard activity.heartbeat with activity.in_activity() in any code path reachable outside an activity. Prefer history-based assertions over tripping timeouts live.
- The gate: root ruff, ruff format --check, mypy strict, and pytest exclude exercises/; `just check` then loops every exercises/*/solution directory running ruff, ruff format --check, mypy, and pytest per directory (so near-identical module names never share one invocation), and the loop is a no-op at exit 0 when no solution directory exists; `just check-practice` loops every exercises/*/practice directory running ruff and mypy only. The observability config tests live under the root tests/ tree and run in the root pytest.
- No role-labeled names (victim, villain, culprit). The fleet reads as ordinary.
- Do not implement anything in Non-goals or either Deferred list: no lab mode, no alert rules or Alertmanager, no ProcessPoolExecutor exercise, no blocking-in-Workflow exercise, no Codespaces, no committed script that reproduces whole runs (the stdlib `scripts/receipt_gaps.py` helper from Section 9 is the one exception), no Web UI screenshots beyond exercise 02's (Section 9), no venue or frontmatter on the drafts.
- Writing hard rules apply to all prose (READMEs, CLAUDE.md, drafts, docstrings, commit messages): no em-dashes or en-dashes, no banned AI-tell vocabulary, straight quotes, one sentence per line in committed Markdown, sentence-case headings for the Temporal education docs.
- Prose steps (11, 12, 13) invoke skills in a fixed order: content-design:tutorial-writing, then voice:teaching, then draft, then content-design:review-content. The tutorial-writing canon wins on mechanics; voice:teaching adds the register. Each prose artifact gets a smell report and an open-questions list in docs/drafts/smell-reports.md, committed with it; the commit on the scaffold branch is the handoff to Mason and nothing publishes from the loop. `just preflight` gates every prose step and is never weakened to pass.
- Vale runs from the repo's own .vale.ini (Step 0), which applies MasonBase everywhere and adds MasonTechnical under docs/drafts/** and exercises/**. Each prose section declares `just lint-prose <its files>` and `just lint-keyboard <its files>` as linters, scoped so a section is never blocked by a file it does not touch; the validator maps Vale error to block, warning to warn, suggestion to info, and every keyboard-characters hit to block. docs/drafts/tutorial-original-draft.md is provenance and is never linted.
- The confirm-at-review decisions baked into this plan: keep max_concurrent_activities=2 and drop its marker (Step 1); metrics port 9465 (Step 3); the slow endpoint served by the starter for exercise 01 (Step 5); the awaited 1-second tick wait with a heartbeat per tick for exercise 02 under a 5-second heartbeat_timeout and an 8-second poll interval (Step 6; this replaced the spec's one-line await, which would still outrun the timeout); the cpu second-Worker demonstration (Steps 7 and 10); the zlib blocker over generated audit-log lines, about 350 ms, for exercise 05 (Step 9, reworked in Section 9); the per-directory mypy and pytest loop (Step 4). Step 10's captures confirmed each, and spec.md now states them as plain decisions; Section 9 supersedes the 02 and 05 designs.
- The full local gate is `just check` plus `just check-practice`; pytest alone (root, which excludes exercises/) is the autonomous-run verification command. The live signatures and after-states are captured in Step 10, not asserted in CI.
- Never commit to main; work on the scaffold branch (PR #4). Only Mason merges to main. No attribution trailers in commits or PRs.

## Success Metrics

- `just check` is green with the solution-copy loop and the observability config tests included, and `just check-practice` is green.
- `grep -rn "slow_heartbeat\|stuck_no_heartbeat\|PriceQuote\|maximum_attempts" src tests justfile` returns nothing.
- `observability/` brings up Prometheus and Grafana with `just metrics` on a docker-compose v1 machine; the config tests pin two scrape targets (9464 and 9465), exactly the two services with no Temporal image, and a dashboard whose panels reference only allowlisted metrics.
- Each of the five exercises runs from its own directory: the practice/ copy reproduces its failure, and the solution/ copy produces its after-state, both captured and quoted. The solution copies pass their Part D tests (probe for 01, 03, 05; heartbeat-and-probe for 02; cancel-stops-work plus executor-size for 04).
- `grep -rn "ANTIPATTERN (deliberate, for teaching)" exercises/*/solution` returns nothing; each practice/ copy keeps its marker and its `# TODO PART X:` comments.
- The root README has exactly three lessons, all recaptured; five exercise READMEs exist in the 102 structure, quote only captures of their own exercise, name the Grafana panel, pass Vale, and have been through /review-content.
- Six tutorial drafts exist under docs/drafts/, follow the tutorial-writing structure, carry no frontmatter, use TODO cross-links, quote only Step 10 captures, pass Vale, and have been through /review-content.
- The root README has the Exercises table and the Observability section; CLAUDE.md describes the trimmed package, the three-layer layout, the solution-copy carve-out, and the new recipes; docs/drafts/README.md lists the six drafts and keeps the venue open.
- `just preflight` exits 0; `just lint-prose` shows no error-level Vale alert across the five exercise READMEs, the six drafts, README.md, CLAUDE.md, and docs/drafts/README.md; `just lint-keyboard` exits 0; docs/drafts/smell-reports.md carries one section per prose artifact with its smell report and open questions.
- The arc ships as commits on the scaffold branch against main, with a session summary per commit.
