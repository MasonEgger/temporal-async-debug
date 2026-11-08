# Session Summary: Step 19 Recapture For The Rework

**Date**: 2026-11-08
**Duration**: not tracked
**Conversation Turns**: autonomous /bpe:goal step (implement, finalize; Tools block is none, so no validator pass)
**Estimated Cost**: not tracked
**Model**: claude-sonnet-5-5

## Goal Context

Driven by `/bpe:goal` over plan.md Section 9 (Post-Review Rework).
This session covers Step 19 only, a task step that recaptures evidence after the exercise 02 retry storm (Step 17) and the exercise 05 audit trail (Step 18).

## Key Actions

- Recaptured exercise 02 practice and solution runs, including Web UI screenshots and the TMPRL1101 lines.
- Recaptured exercise 05 practice and solution runs with the new audit trail.
- Captured the root block histories and the exercise 03 second-Worker run.
- Replaced 16 Grafana PNGs for 02 and 05 and added two Web UI PNGs: `docs/images/02-practice-ui-attempt-2.png` and `docs/images/02-practice-ui-attempt-4.png`.
- The raw captures, INDEX rows, and FINDINGS section live in the scratchpad (`captures/INDEX.md`), not in the repo.
- Checked off Step 19 in `todo.md`. `just check` and `just check-practice` both exit 0.

## Findings

- TMPRL1101 count: 4 of 4 practice runs hit it, one failed Workflow Task each, and TMPRL1104 appeared in every run.

## Open Questions For Mason

<CLAUDE_HELP>
(a) The dashboard failures panel plots `activity_timeout`, which never counts Heartbeat timeouts, so it does not show the exercise 02 storm.
`activity_task_timeout{timeout_type="Heartbeat"}` does count them.
Decide whether the panel should switch to (or add) that series before the Section 10 prose cites the panel for 02.
</CLAUDE_HELP>

<CLAUDE_HELP>
(b) The exercise 03 second-Worker "one slot each" capture cannot be reproduced at the shipped 2 slots.
`--bad 3` spreads the work across the two Workers (top read 96.0 and 93.1 percent).
Decide whether to change the scenario, change the slot count, or drop the claim.
</CLAUDE_HELP>

## Prompt Inventory

| Prompt/Command | Action Taken | Outcome |
|---|---|---|
| mode=implement, Step 19 | Recaptured 02, 05, root, 03; replaced PNGs | Artifacts indexed in scratchpad |
| mode=finalize | Gates, summary, lessons, commit, push | One signed commit |

## Efficiency Insights

- Counting TMPRL1101 and TMPRL1104 per run from the captured histories settled the retry-storm claim quickly.

## Process Improvements

- Check that a dashboard panel shows the symptom before writing prose that cites it. The failures panel missed Heartbeat timeouts.

## Suggested Skills For Next Session

- voice:teaching
- content-design:tutorial-writing
