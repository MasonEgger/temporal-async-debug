"""ABOUTME: Invariant tests for the observability stack under observability/, read as plain text.
ABOUTME: Pins the Prometheus-and-Grafana-only compose file, the two scrape targets, and the dashboard metric allowlist.

Only the stack's invariants are asserted: no Temporal server container, no scrape target beyond the
two metrics endpoints, no dashboard metric outside the allowed list, and a provisioning path that
matches the compose mount. YAML is read with a few regexes because no YAML parser is a dependency.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

OBSERVABILITY_DIR: Path = Path(__file__).resolve().parent.parent / "observability"
"""Root of the compose stack, Prometheus config, and Grafana provisioning."""

ALLOWED_METRICS: frozenset[str] = frozenset(
    {
        "temporal_activity_execution_latency",
        "temporal_workflow_task_schedule_to_start_latency",
        "temporal_workflow_task_execution_latency",
        "temporal_worker_task_slots_used",
        "temporal_activity_execution_failed",
        "temporal_workflow_task_execution_failed",
        "activity_timeout",
    }
)
"""Metric base names a panel may query.

The worker-side set plus the dev server's ``activity_timeout`` counter. A freeze fails no worker-side
activity, so only the server counts the timeout."""

OPTIONAL_BACKLOG_METRICS: frozenset[str] = frozenset({"approximate_backlog_count"})
"""The dev server's Task Queue backlog gauge; its panel may be dropped, so it is allowed but never required."""

HISTOGRAM_SUFFIXES: tuple[str, ...] = ("_bucket", "_sum", "_count")
PROMQL_WORDS: frozenset[str] = frozenset(
    {"by", "without", "on", "ignoring", "group_left", "group_right", "and", "or", "unless", "bool", "offset"}
)


def _code_lines(relative_path: str) -> list[str]:
    """Return the file's lines with comments and blank lines removed.

    Args:
        relative_path: Path relative to ``observability/``.

    Returns:
        The remaining lines, indentation kept, trailing whitespace stripped.
    """
    lines = (line.split(" #")[0].rstrip() for line in (OBSERVABILITY_DIR / relative_path).read_text().splitlines())
    return [line for line in lines if line.strip() and not line.lstrip().startswith("#")]


def _compose_services() -> dict[str, list[str]]:
    """Map each service name under the top-level ``services:`` key to its body lines.

    Returns:
        A dict from service name to that service's stripped body lines.
    """
    services: dict[str, list[str]] = {}
    current: str | None = None
    in_services = False
    for line in _code_lines("docker-compose.yml"):
        if not line.startswith(" "):
            in_services = line.strip() == "services:"
            current = None
        elif in_services and (match := re.fullmatch(r"  (\w[\w-]*):", line)):
            current = match.group(1)
            services[current] = []
        elif in_services and current is not None:
            services[current].append(line.strip())
    return services


def _metric_names(expr: str) -> set[str]:
    """Extract metric names from a PromQL expression, ignoring labels, functions, and durations.

    Args:
        expr: A PromQL expression.

    Returns:
        The set of metric-like tokens left after stripping labels, durations, and keywords.
    """
    stripped = re.sub(r"\{[^}]*\}|\[[^\]]*\]|\"[^\"]*\"", "", expr)
    stripped = re.sub(r"\b(by|without)\s*\([^)]*\)", "", stripped)
    names: set[str] = set()
    for match in re.finditer(r"[A-Za-z_:][A-Za-z0-9_:]*(?!\w)(?!\s*\()", stripped):
        token = match.group(0)
        if token in PROMQL_WORDS:
            continue
        names.add(token)
    return names


def _base_name(name: str) -> str:
    """Map a histogram series name (``_bucket``, ``_sum``, ``_count``) of an allowed metric to its base name.

    Args:
        name: A series name from a PromQL expression.

    Returns:
        The allowlisted base name when a histogram suffix maps to one, otherwise ``name`` unchanged.
    """
    for suffix in HISTOGRAM_SUFFIXES:
        if name.removesuffix(suffix) in ALLOWED_METRICS:
            return name.removesuffix(suffix)
    return name


def _panel_exprs(dashboard: object) -> list[str]:
    """Collect every ``panels[].targets[].expr`` string from a parsed dashboard.

    Args:
        dashboard: The parsed dashboard JSON.

    Returns:
        The expression strings, in panel order. Fails the test if the shape is not as expected.
    """
    assert isinstance(dashboard, dict), "dashboard JSON must be an object"
    panels = dashboard.get("panels", [])
    assert isinstance(panels, list), "panels must be a list"
    exprs: list[str] = []
    for panel in panels:
        assert isinstance(panel, dict), "each panel must be an object"
        targets = panel.get("targets", [])
        assert isinstance(targets, list), "panel targets must be a list"
        for target in targets:
            assert isinstance(target, dict), "each panel target must be an object"
            expr = target.get("expr")
            assert isinstance(expr, str), "each panel target needs a string expr"
            exprs.append(expr)
    return exprs


def _scrape_targets(relative_path: str) -> list[str]:
    """Collect every host:port token on the config's code lines, whatever the YAML shape.

    No structural parsing is done, so block lists, flow lists, quoted values, and any parent shape
    are all seen. A ``*_sd_configs`` key is rejected because service discovery adds targets
    indirectly.

    Args:
        relative_path: Path of the Prometheus config relative to ``observability/``.

    Returns:
        The host:port tokens in file order. Fails the test if a service-discovery key appears.
    """
    code = "\n".join(_code_lines(relative_path))
    assert not re.search(r"_sd_configs", code), "service discovery adds targets the test cannot see"
    return re.findall(r"[A-Za-z0-9_.\-]+:\d{2,5}", code)


def test_compose_runs_only_prometheus_and_grafana() -> None:
    services = _compose_services()

    assert set(services) == {"prometheus", "grafana"}
    images = [line for body in services.values() for line in body if line.startswith("image:")]
    assert images
    assert not [image for image in images if "temporal" in image.lower()]


def test_prometheus_scrapes_exactly_the_sdk_and_dev_server_endpoints() -> None:
    targets = _scrape_targets("prometheus.yml")

    assert sorted(targets) == ["127.0.0.1:9464", "127.0.0.1:9465"]


def test_dashboard_panels_query_only_allowlisted_metrics() -> None:
    dashboards = sorted((OBSERVABILITY_DIR / "grafana" / "dashboards").glob("*.json"))
    assert dashboards

    known = ALLOWED_METRICS | OPTIONAL_BACKLOG_METRICS
    for dashboard_path in dashboards:
        exprs = _panel_exprs(json.loads(dashboard_path.read_text()))
        assert exprs
        for expr in exprs:
            unknown = {name for name in _metric_names(expr) if _base_name(name) not in known}
            assert not unknown, f"{dashboard_path.name}: {expr!r} uses {sorted(unknown)}"


def test_dashboard_provider_path_matches_the_compose_mount() -> None:
    provider_paths = [
        match.group(1)
        for line in _code_lines("grafana/provisioning/dashboards/dashboards.yml")
        if (match := re.fullmatch(r"\s*path:\s*(\S+)", line))
    ]
    mounts = [
        line.removeprefix("- ").strip("\"'")
        for line in _compose_services()["grafana"]
        if line.removeprefix("- ").strip("\"'").startswith("./grafana/dashboards:")
    ]

    assert len(provider_paths) == 1
    assert len(mounts) == 1
    assert mounts[0].split(":")[1] == provider_paths[0]
