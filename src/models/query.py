import json
import logging

import requests

from dependencies import str2bool
from init import CONFIG

GATEWAY_UNREACHABLE = "MyElectricalData injoignable."


def error_detail(response, default=GATEWAY_UNREACHABLE):
    """Extract a human readable error message from a gateway response.

    Args:
        response (requests.Response | None): The response returned by Query (None on network error).
        default (str): Message returned when nothing better is available.

    Returns:
        str: The "detail" field of the JSON body, the raw body, or the default message.
    """
    if response is None or not hasattr(response, "text"):
        return default
    try:
        body = json.loads(response.text)
    except (TypeError, ValueError):
        return response.text or default
    if isinstance(body, dict) and "detail" in body:
        return body["detail"]
    return body or default


class Query(object):
    def __init__(self, endpoint, headers=None):
        self.endpoint = endpoint
        self.timeout = 60
        check_ssl = CONFIG.get("ssl")
        if check_ssl and "gateway" in check_ssl:
            self.ssl_valid = str2bool(check_ssl["gateway"])
        else:
            self.ssl_valid = True
        if not headers:
            self.headers = {"Content-Type": "application/x-www-form-urlencoded"}
        else:
            self.headers = headers

    def _safe_headers(self):
        """Return the headers with secrets masked, for logging purpose."""
        if not isinstance(self.headers, dict):
            return self.headers
        return {key: ("** hidden **" if key.lower() == "authorization" else value) for key, value in self.headers.items()}

    def _request(self, method, params=None, data=None):
        logging.debug(f"[{method}] Endpoint {self.endpoint}")
        logging.debug(f" - headers : {self._safe_headers()}")
        logging.debug(f" - params : {params}")
        if data is not None:
            logging.debug(f" - data : {data}")
        try:
            response = requests.request(
                method,
                headers=self.headers,
                params=params,
                data=data,
                url=self.endpoint,
                timeout=self.timeout,
                verify=self.ssl_valid,
            )
            logging.debug(f"[RESPONSE] : status_code {response.status_code}")
            logging.debug(f" => {response.text}...")
            return response
        except Exception as e:
            logging.error(f"[{method}] {self.endpoint} : {e}")
            return None

    def get(self, params=None):
        return self._request("GET", params=params)

    def post(self, params=None, data=None):
        return self._request("POST", params=params, data=data)

    def delete(self, params=None, data=None):
        return self._request("DELETE", params=params, data=data)

    def put(self, params=None, data=None):
        return self._request("PUT", params=params, data=data)

