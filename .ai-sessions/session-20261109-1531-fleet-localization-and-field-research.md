# Session Summary: Fleet Localization Spec And Field Evidence Review

**Date**: 2026-11-09
**Duration**: about 3 hours
**Conversation Turns**: about 15 user turns
**Estimated Cost**: not tracked precisely; the three research subagents and their helpers used about 2.7M tokens
**Model**: claude-opus-5-5 for most of the session, claude-sonnet-5-5 at the end

## Key Actions

- Read spec.md, todo.md, the recent session records, and the open questions in `docs/drafts/smell-reports.md` to re-establish context; `just check` was green and every todo.md item was checked.
- Compared a field report of a frozen Python Worker fleet against the repository: the mechanism and cross-type blast radius were covered, but finding which Worker in a fleet froze was not.
- Wrote a fleet-localization phase into spec.md, first as a step in exercise 01, then, on Mason's ruling, as a new exercise, `06-finding-the-frozen-worker`, with a synchronous `sqlite3` lock wait as the blocker and an opt-in `--by-identity` view in `scripts/receipt_gaps.py`.
- Ran three read-only research agents to check the exercises against field evidence; stopped one agent at a timeout and recovered its helpers' reports from its transcript.
- Wrote `.ai-sessions/research-20261109-field-evidence.md`, an aggregate-only summary of the evidence with a verdict per exercise and the open decisions.
- Removed every customer reference from spec.md after Mason flagged that the repository is public, and added a Privacy invariant.

## Prompt Inventory

| Prompt/Command | Action Taken | Outcome |
|---|---|---|
| "familiarize yourself with this" | Read spec, todo, sessions, smell reports; ran `just check` | Context summary; nine open questions surfaced |
| Read a field report, is it represented? | Read the report and compared it with the exercises | Covered mechanism; fleet localization and a registration guard missing |
| "Yes, sketch it" | Sketched a two-Worker localization step | Sketch accepted |
| Write it into spec.md, then stop | Edited spec.md in place, linted with a local Vale config | Phase written, not committed |
| Spin up three research agents, ultrathink | Launched three research agents at max effort | About 50 cases across sources |
| Is the slow research agent OK, is it reading too much? | Inspected its transcript | Targeted searches, but it fanned out three helpers |
| Wrap it up, give it a timeout | Sent a wrap-up message, set a 5-minute file watch, stopped it | Helper reports salvaged |
| "Own exercise" | Rewrote the phase as exercise 06 | Spec updated |
| No customer names, not even fake ones | Scrubbed spec.md, added a Privacy invariant and a memory | Repo and history verified clean |
| Commit the spec and research findings | Wrote the research doc, this summary, and the commit | Committed on `scaffold` |

## Efficiency Insights

**What went well:**
- Checking the repo and git history for customer names with one grep settled the privacy question quickly.
- Saving large documents to disk and grepping them kept full documents out of context.

**What could improve:**
- The research briefs did not forbid helper agents, so one agent spawned three and used about 1.3M tokens on its own.
- The first spec draft carried a narrative of a customer case; the Privacy rule should have been applied before writing, not after.

**Course corrections:**
- Fleet localization moved from a step in 01 to its own exercise after the research showed it was a distinct, common skill.
- The spec's starting context was rewritten to describe the gap, not the case that exposed it.

## Process Improvements

- Brief research agents with an explicit budget: no helper agents, a cap on documents read, and a time limit, plus a rule to write findings to disk as they go so a stopped agent loses nothing.
- Apply the Privacy invariant before drafting any spec or prose text that draws on field evidence.

## Observations

- Field diagnosis almost never used the tools the series teaches; teams found blocked loops by asking whether the Activity was `async def` and reading what it called.
- `.vale.ini` hard-codes a Linux `StylesPath`, so `just lint-prose` and `just preflight` fail on macOS.

## Suggested Skills for Next Session

- `content-design:curriculum-design`: the open decisions (exercise order, Part B framing, fold-ins) are curriculum calls.
- `python:python`: exercise 06 copies, the `--by-identity` helper change, and the `sqlite3` spike.
- `temporal:temporal-developer`: the two-Worker capture and Worker identity on history events.
- `content-design:tutorial-writing` and `voice:teaching`: the 06 README and draft part 7, after captures.
