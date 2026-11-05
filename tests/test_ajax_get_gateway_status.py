import logging

import pytest

from tests.conftest import contains_logline


@pytest.mark.parametrize("usage_point_id", [None, "pdl1"])
@pytest.mark.parametrize("response, status_code", [(None, 200), (None, 500), ({"mock": "response"}, 200)])
def test_get_gateway_status(caplog, requests_mock, response, status_code, usage_point_id):
    from models.ajax import Ajax
    from config import URL
    from dependencies import get_version

    requests_mock.get(f"{URL}/ping", json=response, status_code=status_code)

    ajax = Ajax(usage_point_id=usage_point_id) if usage_point_id else Ajax()

    # An invalid (non JSON) response must not raise anymore.
    res = ajax.gateway_status()
    if status_code != 200 or not response:
        assert res == {'information': 'MyElectricalData injoignable.',
                       'status': False,
                       'version': get_version()}
        if status_code == 200:
            assert "Réponse invalide de MyElectricalData" in caplog.text
    else:
        assert res == {'mock': 'response', 'version': get_version()}

    if usage_point_id:
        assert contains_logline(caplog, f"[{usage_point_id.upper()}] CHECK DE L'ÉTAT DE LA PASSERELLE.", logging.INFO)
    else:
        assert contains_logline(caplog, f"CHECK DE L'ÉTAT DE LA PASSERELLE.", logging.INFO)
