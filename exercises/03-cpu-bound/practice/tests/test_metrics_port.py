"""ABOUTME: Tests for the metrics-port setting: resolution, validation, runtime address, banner.
ABOUTME: No server is needed; the telemetry config and the banner are built and read directly.
"""

from __future__ import annotations

import pytest
from temporalio.runtime import PrometheusConfig
from worker import (
    DEFAULT_METRICS_PORT,
    METRICS_PORT_ENV,
    build_telemetry_config,
    print_startup_banner,
    resolve_metrics_port,
)


def test_unset_gives_the_default_port() -> None:
    assert resolve_metrics_port({}) == DEFAULT_METRICS_PORT == 9464


def test_valid_integer_overrides_the_default() -> None:
    assert resolve_metrics_port({METRICS_PORT_ENV: "9466"}) == 9466


@pytest.mark.parametrize("value", ["", "abc", "94.64", "0", "-1", "65536"])
def test_invalid_value_raises_and_names_the_variable(value: str) -> None:
    with pytest.raises(ValueError, match=METRICS_PORT_ENV):
        resolve_metrics_port({METRICS_PORT_ENV: value})


def test_telemetry_config_binds_the_resolved_address() -> None:
    config = build_telemetry_config({METRICS_PORT_ENV: "9466"})
    assert isinstance(config.metrics, PrometheusConfig)
    assert config.metrics.bind_address == "127.0.0.1:9466"


def test_telemetry_config_defaults_to_9464() -> None:
    config = build_telemetry_config({})
    assert isinstance(config.metrics, PrometheusConfig)
    assert config.metrics.bind_address == "127.0.0.1:9464"


def test_banner_prints_the_bound_port(capsys: pytest.CaptureFixture[str]) -> None:
    print_startup_banner(9466)
    assert "http://127.0.0.1:9466/metrics" in capsys.readouterr().out
