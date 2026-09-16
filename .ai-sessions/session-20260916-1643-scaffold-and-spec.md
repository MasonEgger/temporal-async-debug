# Session Summary: Repo Scaffold and Spec for the Async-Blocking Demo

**Date**: 2026-09-16
**Duration**: Multi-day session (2026-09-14 through 2026-09-16), roughly 2-3 active hours
**Conversation Turns**: ~16 user turns touching this repo
**Estimated Cost**: Moderate; three deep-research subagent fan-outs plus interactive spec work
**Model**: Fable 5 (claude-fable-5)

## Key Actions

- Created the repo (git init, `scaffold` branch, no commits to main) with `.gitignore` (commit-msg.md and goal.md ignored for `/bpe:goal` pre-flight), canonical `pyproject.toml` (Python 3.14+, temporalio, httpx), and a `justfile` with demo recipes.
- Drafted `spec.md` from prior deep research (event-loop blocking mechanics, Python 3.14 `asyncio ps`/`pstree` behavior, platform gotchas).
- Ran `/bpe:review` on spec.md (23 decision units); 21 shipped, 2 deferred pending Mason's global request.
- Researched Temporal worker tuning (slots, pollers, schedule-to-start) via temporal-docs MCP and revised the spec: added VictimWorkflow, slow mode, `max_concurrent_activities=2` mistuning, Prometheus metrics endpoint, and the frozen-loop vs slot-exhaustion two-lesson requirement.
- Recorded v2 lab mode in Future work per Mason's rulings: generated fleet as real per-workflow source files (C-Z defaults, no size limit), seeded culprit with reveal command, block+slow modes in v1, FastAPI game-master app for the lab.
- Added the antipattern marker convention: every deliberate bug or mistuning carries `# ANTIPATTERN (deliberate, for teaching): ...` at the offending line, validator-enforced.
- Committed the scaffold locally; remote creation deferred by Mason.

## Prompt Inventory

| Prompt/Command | Action Taken | Outcome |
|---|---|---|
| Set this up with a goal loop | Read bpe goal/plan skill contracts, scaffolded repo + spec | Repo ready for /bpe:plan |
| /bpe:review (spec) | Served 23-unit review page | 21 ship, 2 update, global fleet request |
| Multi-workflow contagion request | Worker-tuning research, spec revision | Two-lesson design (freeze vs slots) |
| Fleet/misbehavior/lab questions | AskUserQuestion round | Generated fleet, block+slow, lab in v2 |
| Antipattern comment concern | Spec marker convention + training-pollution discussion | Line-level greppable markers required |
| FastAPI UI question | Assessment + spec future-work update | CLI-only v1; FastAPI game master in v2 lab |
| Use local git for now | Ran commit sequence | Scaffold committed on `scaffold` branch |

## Efficiency Insights

**What went well:**
- Reading the goal/plan skill contracts before scaffolding meant the repo passed every pre-flight requirement by construction (gitignore entries, pyproject autodetect, branch discipline).
- The review page's fine-grained units surfaced the fleet idea early, before any code existed.

**What could improve:**
- The spec was revised three times post-review (contagion, markers, FastAPI); batching Mason's open questions before the first `/bpe:review` would have saved a cycle.

**Course corrections:**
- Flask UI dropped, reconsidered twice, settled as: CLI-only v1, FastAPI game master in v2.
- Fleet generation chosen over hand-written cast, reconciled with the stack-trace-clue requirement by generating real per-file sources.

## Process Improvements

- When a spec review comment says "wait for my other request", treat the global comment as the primary feedback and do its research before applying any unit-level feedback.
- For teaching repos, write the antipattern marker convention into the spec before any code exists so the validator enforces it from step one.

## Observations

- The worker-tuning research materially changed the design: slot exhaustion (worker stops polling, vanishes from the UI poller list) is a second, distinct lesson from the frozen loop, and the spec now requires the two to be distinguishable purely from tool output.
- `schedule_to_start_timeout` on the victim is itself an antipattern used deliberately to make failure legible; it carries the marker comment.

## Suggested Skills for Next Session

- `python:python`: first implementation steps create the package, dataclasses, and tests under the canonical toolchain.
- `temporal:temporal-developer`: worker configuration, ActivityEnvironment/WorkflowEnvironment testing, heartbeat and timeout semantics.
