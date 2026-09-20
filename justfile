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

# Trigger a healthy fleet: geo-enrichment and order-receipt runs, all completing
trigger:
    uv run python -m temporal_async_debug.starter --geo 2 --receipts 3

# Trigger a fleet where one geo run blocks the event loop, freezing the whole worker (frozen-loop lesson)
block seconds="30":
    uv run python -m temporal_async_debug.starter --mode block --block-seconds {{seconds}} --bad 1 --geo 2 --receipts 3

# Trigger a fleet where two slow geo runs hold both slots, starving the rest (slot-exhaustion lesson)
slow seconds="30":
    uv run python -m temporal_async_debug.starter --mode slow --block-seconds {{seconds}} --bad 2 --geo 2 --receipts 3
