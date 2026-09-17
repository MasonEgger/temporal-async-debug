"""ABOUTME: Workflow tests for VictimWorkflow under a time-skipping WorkflowEnvironment.
ABOUTME: quick_task is the real activity; it does no network, so no test touches the wire.

The happy path proves the victim runs its one fast activity and threads the result into the
output message. The concurrent path proves several victims run independently and keep their
labels distinct, which is the property the demo relies on when the misbehaving worker stalls.
"""

from __future__ import annotations

import asyncio
import uuid

from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from temporal_async_debug.shared import TASK_QUEUE, VictimInput, VictimOutput
from temporal_async_debug.victim import VictimWorkflow, quick_task


async def test_victim_workflow_happy_path_includes_label_and_result() -> None:
    """The victim runs quick_task and returns a message carrying the label and its result."""
    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[VictimWorkflow],
            activities=[quick_task],
        ),
    ):
        result = await env.client.execute_workflow(
            VictimWorkflow.run,
            VictimInput(label="check-1"),
            id=str(uuid.uuid4()),
            task_queue=TASK_QUEUE,
        )

    assert isinstance(result, VictimOutput)
    # The label appears in the message and the quick_task return value flows through unchanged,
    # which proves the activity ran and produced its fast, network-free result.
    assert "check-1" in result.message
    assert "processed check-1" in result.message


async def test_victim_workflows_run_concurrently_with_distinct_labels() -> None:
    """Several victims run concurrently, each completing with its own label reflected in the output."""
    labels = [f"check-{run_index}" for run_index in range(5)]
    """Distinct labels, one per concurrent victim run, checked back out of the results."""

    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[VictimWorkflow],
            activities=[quick_task],
        ),
    ):
        results = await asyncio.gather(
            *(
                env.client.execute_workflow(
                    VictimWorkflow.run,
                    VictimInput(label=label),
                    id=str(uuid.uuid4()),
                    task_queue=TASK_QUEUE,
                )
                for label in labels
            )
        )

    assert all(isinstance(result, VictimOutput) for result in results)
    # Each victim kept its own label, so the set of labels in the outputs matches the inputs.
    assert {result.message for result in results} == {f"victim {label}: processed {label}" for label in labels}
