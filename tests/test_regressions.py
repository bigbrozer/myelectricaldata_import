"""Regression tests for bugs fixed in the src/ review (Phase 1)."""

import pytest


YAML = """cycle: 3600
# comment
foo_cycle: 1
home_assistant_ws:
  enable: true
  purge: true
other:
  purge: true
wipe_influxdb: true
"""


@pytest.mark.parametrize(
    "path, expected_line, untouched_line",
    [
        ("home_assistant_ws.purge", "  purge: false", "other:\n  purge: true"),
        ("cycle", "cycle: false", "foo_cycle: 1"),
        ("wipe_influxdb", "wipe_influxdb: false", "home_assistant_ws:\n  enable: true\n  purge: true"),
    ],
)
def test_config_set_only_updates_the_exact_key(path, expected_line, untouched_line):
    from models.config import Config

    result = Config._replace_yaml_value(YAML, path.split("."), "false")

    assert expected_line in result
    assert untouched_line in result
    assert "# comment" in result


def test_str2bool_and_is_bool():
    from dependencies import is_bool, str2bool

    assert str2bool("True") is True
    assert str2bool(1) is True
    assert str2bool(None) is False
    assert str2bool("no") is False
    assert is_bool("yes") and is_bool("False") and is_bool(0)
    assert not is_bool("maybe") and not is_bool(2.5)
