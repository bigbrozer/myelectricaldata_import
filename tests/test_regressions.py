"""Regression tests for bugs fixed in the src/ review (Phase 1)."""

import dataclasses

import pytest


@dataclasses.dataclass
class MockResponse:
    status_code: int
    text: str = ""

    @property
    def ok(self):
        return 200 <= self.status_code < 400


@pytest.mark.parametrize(
    "response, expected",
    [
        (None, "MyElectricalData injoignable."),
        (MockResponse(500, '{"detail": "boom"}'), "boom"),
        (MockResponse(502, "<html>Bad Gateway</html>"), "<html>Bad Gateway</html>"),
        (MockResponse(500, ""), "MyElectricalData injoignable."),
    ],
)
def test_error_detail(response, expected):
    from models.query import error_detail

    assert error_detail(response) == expected


def test_query_masks_authorization_header():
    from models.query import Query

    query = Query("http://localhost", headers={"Authorization": "secret", "version": "1"})
    assert query._safe_headers() == {"Authorization": "** hidden **", "version": "1"}


def test_status_network_error_has_job_compatible_shape(mocker):
    from models.query_status import Status

    mocker.patch("models.query.Query.get", return_value=None)
    status = Status().status("pdl1")

    assert status["error"] is True
    assert status["status_code"] == 500
    assert status["description"]["detail"] == "MyElectricalData injoignable."


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
