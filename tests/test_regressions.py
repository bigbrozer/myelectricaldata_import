"""Regression tests for bugs fixed in the src/ review (Phase 1)."""

import dataclasses
from datetime import datetime

import pytest


@dataclasses.dataclass
class MockResponse:
    status_code: int
    text: str = ""

    @property
    def ok(self):
        return 200 <= self.status_code < 400


def test_job_import_data_releases_lock_when_an_exporter_raises(mocker):
    from init import DB
    from models.jobs import Job

    for method in ["get_gateway_status", "get_tempo", "get_ecowatt"]:
        mocker.patch(f"models.jobs.Job.{method}")
    mocker.patch("models.jobs.Job.get_account_status", side_effect=RuntimeError("boom"))

    job = Job("pdl1")
    with pytest.raises(RuntimeError):
        job.job_import_data(wait=False, target="account_status")

    assert DB.lock_status() is False


def test_export_home_assistant_ws_errors_are_caught(mocker, caplog):
    from models.jobs import Job

    mocker.patch("models.jobs.HomeAssistantWs", side_effect=AttributeError("websocket is None"))
    job = Job("pdl1")
    job.usage_point_config = job.usage_points[0]
    job.home_assistant_ws_config = {"enable": "true"}

    job.export_home_assistant_ws()

    assert "websocket is None" in caplog.text


def test_stat_last_year_covers_the_whole_year():
    from models.stat import Stat

    last_year = Stat("pdl1", "consumption").last_year()

    year = datetime.now().year - 1
    assert last_year["begin"] == f"{year}-01-01"
    assert last_year["end"] == f"{year}-12-31"


def test_stat_yearly_evolution_without_previous_year():
    from models.stat import Stat

    stat = Stat("pdl1", "consumption")
    stat.current_year = lambda: None
    stat.current_year_last_year = lambda: None
    stat.value_current_year = 1000
    stat.value_current_year_last_year = 0
    stat.value_last_month_last_year = 10

    assert stat.yearly_evolution() == 0


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


def test_error_response_exit_on_403():
    from models.query import error_response

    assert error_response(MockResponse(403, '{"detail": "forbidden"}')) == {
        "error": True,
        "description": "forbidden",
        "status_code": 403,
        "exit": True,
    }
    assert error_response(None)["status_code"] == 500


def test_query_masks_authorization_header():
    from models.query import Query

    query = Query("http://localhost", headers={"Authorization": "secret", "version": "1"})
    assert query._safe_headers() == {"Authorization": "** hidden **", "version": "1"}


def test_daily_get_survives_gateway_errors(mocker):
    from models.query_daily import Daily

    mocker.patch("models.query.Query.get", return_value=None)
    daily = Daily(headers={}, usage_point_id="pdl1")
    daily.activation_date = None

    # Error payloads must never end up in the returned list.
    assert daily.get() == []


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


def test_influxdb_production_detail_export(mocker):
    from models.export_influxdb import ExportInfluxDB

    @dataclasses.dataclass
    class Detail:
        date: datetime
        value: int = 1000
        interval: int = 30

    rows = [Detail(datetime(2024, 1, 1, 0, 0)), Detail(datetime(2024, 1, 1, 0, 30))]
    mocker.patch("models.database.Database.get_detail_all", return_value=rows)
    mocker.patch("models.database.Database.get_detail_last_date", return_value=rows[0].date)
    mocker.patch("models.database.Database.get_detail_first_date", return_value=rows[-1].date)
    influxdb = mocker.patch("models.export_influxdb.INFLUXDB")
    influxdb.count.return_value = []

    @dataclasses.dataclass
    class UsagePointConfig:
        usage_point_id: str = "pdl1"
        production_price: float = 0.1

    ExportInfluxDB({}, UsagePointConfig()).detail(measurement_direction="production")

    assert influxdb.write.call_count == 2
    assert influxdb.write.call_args.kwargs["measurement"] == "production_detail"
    assert influxdb.write.call_args.kwargs["tags"]["measure_type"] == "PROD"
