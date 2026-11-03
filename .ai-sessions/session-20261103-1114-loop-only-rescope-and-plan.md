# Session Summary: Loop-Only Rescope And Exercises Plan Review

**Date**: 2026-11-03
**Duration**: Long; two calendar days across a context compaction (November 2 rescope, November 3 review and apply)
**Conversation Turns**: Many
**Estimated Cost**: Medium to high (two review pages, a spec rewrite, a plan regeneration, and a full apply-review)
**Model**: Opus 4.8 and Opus 5.5 for the review pages and the rescope; Fable 5.1 for `/bpe:apply-review` (matching its profile pin); Sonnet 5.5 for this summary

## Key Actions

- Archived the finished catalog plan to `.ai-sessions/failure-mode-catalog/` (`plan.md`, `todo.md`, and a fresh `accomplishment.md`) ahead of the regeneration.
- Built the plan review page and widened it twice; the BPE `review.css` caps `.review-section` at 760px and `.prose` at 68ch, and a `<style>` override placed after the injected CSS was what fixed the cramped layout.
- Defended the timeout and retry lessons on merit and was overruled on scope: Mason ruled the series is only about blocking the shared asyncio event loop.
- Rewrote `spec.md` to that scope (a new scope invariant, `VALID_MODES` down to `block` and `cpu`, `quote.py` and `maximum_attempts=1` removed, five loop-only exercises, the saturation and heartbeat lessons moved to Non-goals).
- Mason ran `/bpe:plan --regen`; the plan came back as 13 steps, then grew a Step 0 (Vale config and the prose preflight gate) on the morning of November 3.
- Restarted the review server after it died overnight; a `pkill -f review-server.py` matched the calling shell's own command line and killed it too.
- Rebuilt the review page from the regenerated plan with a small Python markdown script (17 units, 9 groups) after noticing the plan's mtime was newer than the page.
- Applied the review: 10 Ship it, 7 Close but update; renamed exercise 04 from `half-fixes` to `zombie-thread`, wrote the execution-failure bar into the spec's Invariants and the plan's guidelines, trimmed the observability config tests to invariants only, gave exercise 05 a real symptom (receipts visibly delayed), and made Part B of every README the Python-tooling diagnosis with Grafana last.
- Changed the exercise 02 fix from the spec's one-line `await asyncio.sleep(poll_interval)` to awaited 1-second ticks with a heartbeat per tick, because the one-liner still outruns a heartbeat timeout shorter than the poll interval; marked confirm-at-review in both files.
- Mirrored every plan change into `todo.md` and `spec.md` so the executor and validator read one story.

## Prompt Inventory

| Prompt/Command | Action Taken | Outcome |
|---|---|---|
| Screenshot: "page is too narrow and things get cut off" | Widened `.review-layout` and the prose measure | Still gappy |
| Screenshot: "Still looks stupid, so much gap" | Overrode the 760px section cap and the prose measure after the injected CSS | Fixed |
| "are all the things we're teaching here related to the async event loop being blocked?" | Defended keeping exercise 05 and the timeout content | Rejected |
| "Sigh no, that was not the point ... JUST about the Python async event loop" | Stopped defending; proposed the loop-only scope | Rescope agreed |
| "I want the exercises that show off the most likely things a user would trip on" | Drew the five exercises from the temporal-docs community threads | Exercise set settled |
| "how much needs to be changed? How much wasted effort?" | Costed the rescope: spec sections, plan regeneration, no code yet | Proceeded |
| "Update the spec and then let's regenerate the plan" | Rewrote `spec.md` in place | Spec updated |
| `/bpe:plan --regen` (run by Mason) | Plan and todo regenerated | 13 steps, later 14 |
| `/bpe:review plan` | Built and served the review page | Served |
| "Not working. Kill and try again" | Killed the servers (and my own shell once), restarted | Served, then died unsaved overnight |
| "Where did the contract task go? Put that today" | Looked it up in Todoist | Already due today; left as is |
| "Are we ready to kick off the goal loop?" | Checked: review unsaved, tree dirty | Not yet; listed the order |
| "host the plan again ... Or do you think we've iterated on this enough?" | Rebuilt the page from the newer plan; recommended one short pass | Review saved: 10 ship, 7 update |
| `/bpe:apply-review and follow up with my inqueries` | Summarized, answered the four questions inline, proposed the edits and the rename | Approved |
| "I like the rename ... Any edits you think we need to add, do that" | Applied all seven units plus the 02 fix correction across plan, todo, and spec | Done |
| "do the commit and let's get ready to run bpe:goal" | This summary, then the commit sequence | In progress |

## Efficiency Insights

**What went well:**
- Answering the review's four questions inline, with the concrete edit each answer implied, got the whole review approved in one turn.
- Checking the plan's mtime against the review page caught a Step 0 the old page would have hidden from the reviewer.
- Generating the review HTML with a script instead of by hand made the rebuild one command.

**What could improve:**
- The timeout and retry content was defended on value when the test was scope; one re-read of Mason's one-sentence scope statement would have saved the argument and the regeneration.
- `pkill -f` with a pattern that matches the calling shell is a self-kill; the PID file was there for exactly this.
- The review server was left running overnight and died before a save; restarting it right before the review session would have avoided the stale URL.

**Course corrections:**
- From a mixed catalog (freeze, saturation, heartbeat, retry) to one mechanism, the blocked event loop.
- Exercise 04 from "half fixes" (Mason: goofy) to the real problem it demonstrates, the activity running twice because the cancel never reaches the detached thread.
- Exercise 02's fix from the one-line await to awaited short ticks with a heartbeat per tick.

## Process Improvements

- Write a scope bar into `## Invariants` as soon as the owner states it in one sentence; the plan writer and validator then enforce it mechanically instead of the reviewer catching drift by hand.
- When a review unit is a question, answer it in the apply-review summary and state the edit the answer implies, rather than treating the comment as a directive to paraphrase.
- Before re-serving a review page, compare the artifact's mtime to the page's; rebuild when the artifact is newer.

## Observations

- Several "confirm at review" decisions in the plan depend on the Step 10 captures: the 02 tick-loop fix and its 5-second timeout against an 8-second poll, the 05 receipt delay, the backlog gauge, and port 9465.
- The 02 heartbeat reasoning (the Python SDK schedules the heartbeat send as an asyncio task, so it cannot leave a frozen loop) is from reading the SDK, not from a capture; Step 10 is where it gets confirmed.
- The spec and plan now both carry the rule that exercise 05 is the only one allowed to misbehave without failing.

## Suggested Skills for Next Session

- `content-design:style-linting`: the goal loop's first step (Step 0) writes `.vale.ini` and the `just preflight` gate.
- `python:python` and `temporal:temporal-developer`: Step 1 trims the root package and must preserve the `block` and `cpu` behavior.
- `mcp__temporal-docs__search_temporal_knowledge_sources`: confirm the heartbeat-task behavior and the sync-activity-on-executor pattern before Steps 5 to 9 apply the fixes.
