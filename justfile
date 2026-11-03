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

# Start the local Temporal dev server (leave running in its own terminal)
server:
    temporal server start-dev --metrics-port 9465

# Bring up the Prometheus and Grafana stack in the background (docker-compose v1)
metrics:
    docker-compose -f observability/docker-compose.yml up -d

# Tear down the Prometheus and Grafana stack
metrics-down:
    docker-compose -f observability/docker-compose.yml down

# Start the demo worker (prints its PID for asyncio introspection)
worker:
    uv run python -m temporal_async_debug.worker

# Trigger a small healthy fleet: geo-enrichment and order-receipt runs, all completing
trigger:
    uv run python -m temporal_async_debug.starter --geo 2 --receipts 3

# Trigger the full healthy fleet: geo, rollup, and receipt runs, all completing
healthy:
    uv run python -m temporal_async_debug.starter --geo 2 --rollups 1 --receipts 3

# Trigger a fleet where one geo run blocks the event loop, freezing the whole worker (frozen-loop lesson)
block seconds="30":
    uv run python -m temporal_async_debug.starter --mode block --block-seconds {{seconds}} --bad 1 --geo 1 --rollups 1 --receipts 2

# Trigger a fleet where one geo run pins the GIL in a busy loop, freezing the whole worker (CPU-pinned lesson)
cpu seconds="30":
    uv run python -m temporal_async_debug.starter --mode cpu --block-seconds {{seconds}} --bad 1 --geo 1 --rollups 1 --receipts 2
