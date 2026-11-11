"""ABOUTME: Invariant tests for the observability stack under observability/, read as plain text.
ABOUTME: Pins the Prometheus-and-Grafana-only compose file, the three scrape targets, and the dashboard panels.

Only the stack's invariants are asserted: no Temporal server container, no scrape target beyond the
two Worker endpoints and the dev server, no dashboard metric outside the allowed list, the per-Worker
panel, the pinned expressions of panels 1 to 6, and a provisioning path that matches the compose
mount. YAML is read with a few regexes because no YAML parser is a dependency.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from temporal_async_debug.shared import TASK_QUEUE

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

DASHBOARD_PATH: Path = OBSERVABILITY_DIR / "grafana" / "dashboards" / "async-debug.json"
"""The one provisioned dashboard."""

PER_WORKER_SLOTS_EXPR: str = (
    'temporal_worker_task_slots_used{worker_type="WorkflowWorker", task_queue="async-debug-task-queue"}'
)
"""The per-Worker panel's query: one Workflow Task slots line per scraped Worker, never summed."""

PINNED_PANEL_EXPRS: tuple[str, ...] = (
    "rate(temporal_activity_execution_latency_sum[30s]) / rate(temporal_activity_execution_latency_count[30s])",
    "rate(temporal_workflow_task_schedule_to_start_latency_sum[30s])"
    " / rate(temporal_workflow_task_schedule_to_start_latency_count[30s])",
    "rate(temporal_workflow_task_execution_latency_sum[30s])"
    " / rate(temporal_workflow_task_execution_latency_count[30s])",
    "increase(temporal_activity_execution_failed[1m])",
    "increase(temporal_workflow_task_execution_failed[1m])",
    "sum by (timeout_type) (activity_timeout)",
    "sum by (worker_type) (temporal_worker_task_slots_used)",
    'sum by (task_type) (approximate_backlog_count{taskqueue="async_debug_task_queue"})',
)
"""The expressions of panels 1 to 6, pinned verbatim."""

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


def _panels(dashboard: object) -> list[dict[str, object]]:
    """Return the ``panels`` list of a parsed dashboard.

    Args:
        dashboard: The parsed dashboard JSON.

    Returns:
        The panel objects, in file order. Fails the test if the shape is not as expected.
    """
    assert isinstance(dashboard, dict), "dashboard JSON must be an object"
    panels = dashboard.get("panels", [])
    assert isinstance(panels, list), "panels must be a list"
    for panel in panels:
        assert isinstance(panel, dict), "each panel must be an object"
    return panels


def _panel_targets(dashboard: object) -> list[dict[str, object]]:
    """Collect every ``panels[].targets[]`` object from a parsed dashboard.

    Args:
        dashboard: The parsed dashboard JSON.

    Returns:
        The target objects, in panel order. Fails the test if the shape is not as expected.
    """
    collected: list[dict[str, object]] = []
    for panel in _panels(dashboard):
        targets = panel.get("targets", [])
        assert isinstance(targets, list), "panel targets must be a list"
        for target in targets:
            assert isinstance(target, dict), "each panel target must be an object"
            assert isinstance(target.get("expr"), str), "each panel target needs a string expr"
            collected.append(target)
    return collected


def _panel_exprs(dashboard: object) -> list[str]:
    """Collect every ``panels[].targets[].expr`` string from a parsed dashboard.

    Args:
        dashboard: The parsed dashboard JSON.

    Returns:
        The expression strings, in panel order. Fails the test if the shape is not as expected.
    """
    return [str(target["expr"]) for target in _panel_targets(dashboard)]


def _per_worker_slots_target() -> dict[str, object]:
    """Return the one dashboard target that selects the ``WorkflowWorker`` slots gauge.

    Returns:
        The target object. Fails the test unless exactly one target selects that gauge.
    """
    matches = [
        target
        for target in _panel_targets(json.loads(DASHBOARD_PATH.read_text()))
        if 'worker_type="WorkflowWorker"' in str(target["expr"])
    ]
    assert len(matches) == 1, f"expected one WorkflowWorker slots target, found {len(matches)}"
    return matches[0]


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


def test_prometheus_scrapes_both_worker_endpoints_and_the_dev_server() -> None:
    targets = _scrape_targets("prometheus.yml")

    assert sorted(targets) == ["127.0.0.1:9464", "127.0.0.1:9465", "127.0.0.1:9466"]


def test_one_panel_draws_workflow_task_slots_per_worker() -> None:
    target = _per_worker_slots_target()
    expr = str(target["expr"])

    assert not re.match(r"\s*sum\b", expr), f"summing would merge the Workers into one line: {expr!r}"
    assert expr == PER_WORKER_SLOTS_EXPR
    assert target.get("legendFormat") == "{{instance}}"


def test_per_worker_panel_filters_on_the_demo_task_queue() -> None:
    expr = str(_per_worker_slots_target()["expr"])
    queue_match = re.search(r'task_queue="([^"]*)"', expr)

    assert queue_match is not None, f"no task_queue filter in {expr!r}"
    assert queue_match.group(1) == TASK_QUEUE


def test_panels_one_to_six_keep_their_pinned_expressions() -> None:
    exprs = _panel_exprs(json.loads(DASHBOARD_PATH.read_text()))

    missing = [expr for expr in PINNED_PANEL_EXPRS if expr not in exprs]
    assert not missing, f"panel expressions changed or removed: {missing}"


def test_dashboard_panel_ids_are_unique() -> None:
    panel_ids = [panel.get("id") for panel in _panels(json.loads(DASHBOARD_PATH.read_text()))]

    assert len(panel_ids) == len(set(panel_ids)), f"duplicate panel ids: {panel_ids}"


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
