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

# Trigger a healthy (non-blocking) workflow run
trigger name="friend":
    uv run python -m temporal_async_debug.starter --name {{name}}

# Trigger a run whose activity blocks the event loop (frozen-loop lesson)
block seconds="30" name="friend":
    uv run python -m temporal_async_debug.starter --name {{name}} --mode block --block-seconds {{seconds}} --victims 3

# Trigger slow cooperative runs that exhaust the worker's two slots (slot-exhaustion lesson)
slow seconds="30" name="friend":
    uv run python -m temporal_async_debug.starter --name {{name}} --mode slow --block-seconds {{seconds}} --count 2 --victims 3
