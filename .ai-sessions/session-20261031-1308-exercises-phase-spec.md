# Session Summary: Exercises Phase Spec

**Date**: 2026-10-31
**Duration**: Long; a tutorial outline, its reversal, and a merge-mode brainstorm across three calendar days
**Conversation Turns**: Many, in a context continued from the catalog arc
**Estimated Cost**: Medium
**Model**: Fable 5.1 for most of the session; Opus 4.8 for the brainstorm's opening checks until the session was switched back to Fable 5.1

## Key Actions

- Read the tutorial-writing skill references and the full README, verified the six py-spy line anchors still match HEAD, and wrote a seven-part series outline to `docs/drafts/output/outline.md`.
- The outline was superseded before any section was written: Mason ruled that every tutorial part must have the reader observe, find, and fix a bug, and that fixes live in Temporal 101/102 style `practice/` and `solution/` directories per exercise.
- Checked Temporal's sync-versus-async guidance through the temporal-docs MCP (plain `def` Activities on a `ThreadPoolExecutor` are the recommended fix; `ProcessPoolExecutor` is discouraged), confirmed `temporal server start-dev --metrics-port`, and confirmed `docker` plus `docker-compose` v1 on the capture machine with `ptrace_scope` at 0.
- Read `~/Code/Temporal/edu-102-python-code` for the exercise layout (README with Parts A to E, `practice/` with `TODO PART X` comments, `solution/` completed) and saved it to memory as a standing preference.
- Ran `/bpe:brainstorm` in merge mode and added the `exercises-and-observability` phase to `spec.md`: five exercises, a Prometheus and Grafana stack over the SDK and dev-server metrics, fresh before-and-after captures, six tutorial drafts, widened invariants (start-dev only, 102 layout, solution-copy marker carve-out, captured-output-only, no new Python deps), and the catalog moved to Shipped.
- Gitignored `docs/drafts/output/` and kept the work on `scaffold` (PR 4) after Mason declined a second branch.

## Prompt Inventory

| Prompt/Command | Action Taken | Outcome |
|---|---|---|
| Continue the seven-part outline (from the compacted context) | Read references and README, verified line anchors, wrote the outline | Outline written, then superseded |
| AskUserQuestion: outline approval, fix presentation, series title, repo URL | Approved; fix answer redefined the deliverable (observe, find, fix in every part; maybe Grafana) | Outline reopened |
| AskUserQuestion: Grafana, fix mechanics, structure, process | Include Grafana; follow the 101/102 practice/solution methodology; six parts; BPE plan and goal loop | Design settled |
| `/bpe:brainstorm let's settle the last things you need` | Merge-mode Q&A, constraints and adjacency passes, merged spec written to scratch, diff shown, moved over spec.md | spec.md updated |
| "be sure you're using the temporal dev server single binary CLI" | Recorded as an invariant: start-dev only, no cluster, no server container | In spec |
| "Wait let's stop. Tell me what's going on." | Stopped asking, stated the state and the remaining three steps | Resumed on one branch |
| "Get everything in order on one branch" | Stayed on `scaffold`, gitignored the output directory, committed the spec | This commit |

## Efficiency Insights

**What went well:**
- Verifying the py-spy line anchors against HEAD before outlining cost one grep and would have caught any drift before it reached prose.
- The 102 repo on disk gave the exercise layout in one diff, with no guessing about the TODO convention.

**What could improve:**
- The outline was written before the deliverable's shape was confirmed; one question ("does every part end with the reader fixing code?") before outlining would have saved the whole draft.
- Too many forks went to AskUserQuestion. Ports, slot counts, gitignore lines, and the branch name were defaults, not decisions, and the fourth round prompted Mason to stop the session.

**Course corrections:**
- Dropped the seven-part observe-and-read outline for six observe-find-fix parts with five exercises.
- Dropped the proposed `exercises` branch; everything stays on `scaffold`.

## Process Improvements

- Before any tutorial outline, confirm the reader's deliverable (what they change, where the fixed code lives) and the venue; record both in the spec first.
- In merge-mode brainstorms, record low-stakes values as `confirm at review` and ask only the forks that change the plan's shape.

## Observations

- The brainstorm profile pins Fable 5.1; the session was on Opus 4.8 when it started and the note was stated per the hook before continuing.
- `spec.md` grew from 275 to 421 lines; the only removed text was the catalog's build-target architecture, whose behavior statements live in Behavior requirements.

## Suggested Skills for Next Session

- `bpe:plan` (with `--archive`, slug `failure-mode-catalog`): turn the merged spec into the exercises plan.
- `python:python`: the exercise copies and the config tests.
- `content-design:tutorial-writing` and `content-design:review-content`: the exercise READMEs and the six drafts, after the captures exist.
