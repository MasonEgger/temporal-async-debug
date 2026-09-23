# ABOUTME: Task runner recipes; `just check` is the local gate (no pre-commit).
# ABOUTME: Demo recipes start the Temporal dev server, the worker, and workflow triggers.

default:
    @just --list

check:
    uv run ruff check .
    uv run ruff format --check .
    uv run mypy .
    uv run pytest

fmt:
    uv run ruff format .
    uv run ruff check --fix .

test:
    uv run pytest

# Start the local Temporal dev server (leave running in its own terminal)
server:
    temporal server start-dev

# Start the demo worker (prints its PID for asyncio introspection)
worker:
    uv run python -m temporal_async_debug.worker

# Trigger a small healthy fleet: geo-enrichment and order-receipt runs, all completing
trigger:
    uv run python -m temporal_async_debug.starter --geo 2 --receipts 3

# Trigger the full healthy fleet: geo, rollup, receipt, and quote runs, all completing
healthy:
    uv run python -m temporal_async_debug.starter --geo 2 --rollups 1 --receipts 3 --quotes 1

# Trigger a fleet where one geo run blocks the event loop, freezing the whole worker (frozen-loop lesson)
block seconds="30":
    uv run python -m temporal_async_debug.starter --mode block --block-seconds {{seconds}} --bad 1 --geo 1 --rollups 1 --receipts 2

# Trigger a fleet where one geo run pins the GIL in a busy loop, freezing the whole worker (CPU-pinned lesson)
cpu seconds="30":
    uv run python -m temporal_async_debug.starter --mode cpu --block-seconds {{seconds}} --bad 1 --geo 1 --rollups 1 --receipts 2

# Trigger a fleet where two slow geo runs hold both slots, starving the rest (slot-exhaustion lesson)
slow seconds="30":
    uv run python -m temporal_async_debug.starter --mode slow --block-seconds {{seconds}} --bad 2 --geo 1 --rollups 1 --receipts 2 --quotes 1

# Trigger a fleet where two correctly-heartbeating geo runs still saturate an undersized worker (slot-exhaustion lesson, no bug in the bad run itself)
slow-heartbeat seconds="30":
    uv run python -m temporal_async_debug.starter --mode slow_heartbeat --block-seconds {{seconds}} --bad 2 --receipts 2 --rollups 1

# Trigger a fleet where a geo run holds a slot without heartbeating, tripping a heartbeat timeout (heartbeat-loss lesson)
stuck seconds="30":
    uv run python -m temporal_async_debug.starter --mode stuck_no_heartbeat --block-seconds {{seconds}} --bad 1 --geo 1
