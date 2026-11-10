from __future__ import annotations

import unittest
from unittest.mock import patch

from requests import Session

from codex_seo_mcp.clients.ga4_transport import Ga4HttpTransport
from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode


class FakeResponse:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession(Session):
    def __init__(self, response: FakeResponse) -> None:
        super().__init__()
        self.response = response
        self.get_calls: list[tuple[str, dict[str, object], float]] = []
        self.post_calls: list[tuple[str, dict[str, object], float]] = []

    def get(self, url: str, *, params: dict[str, object], timeout: float):
        self.get_calls.append((url, params, timeout))
        return self.response

    def post(self, url: str, *, json: dict[str, object], timeout: float):
        self.post_calls.append((url, json, timeout))
        return self.response


class Ga4HttpTransportTests(unittest.TestCase):
    def test_admin_get_builds_admin_endpoint_without_mapping_payload(self) -> None:
        session = FakeSession(FakeResponse(200, {"accountSummaries": []}))
        transport = Ga4HttpTransport(
            admin_base_url="https://admin.test/v1beta",
            data_base_url="https://data.test/v1beta",
            timeout_seconds=7,
        )

        with patch(
            "codex_seo_mcp.clients.ga4_transport._authorized_session",
            return_value=session,
        ):
            payload = transport.admin_get(
                object(),
                "/accountSummaries",
                params={"pageSize": 200},
            )

        self.assertEqual(payload, {"accountSummaries": []})
        self.assertEqual(
            session.get_calls,
            [
                (
                    "https://admin.test/v1beta/accountSummaries",
                    {"pageSize": 200},
                    7,
                )
            ],
        )

    def test_data_post_maps_permission_error_to_stable_error_code(self) -> None:
        session = FakeSession(FakeResponse(403, {}))
        transport = Ga4HttpTransport(
            admin_base_url="https://analyticsadmin.googleapis.com/v1beta",
            data_base_url="https://analyticsdata.googleapis.com/v1beta",
            timeout_seconds=30,
        )

        with patch(
            "codex_seo_mcp.clients.ga4_transport._authorized_session",
            return_value=session,
        ):
            with self.assertRaises(SeoDataError) as caught:
                transport.data_post(
                    object(),
                    "/properties/222:runReport",
                    body={"metrics": []},
                )

        self.assertEqual(caught.exception.code, SeoDataErrorCode.PERMISSION_DENIED)


if __name__ == "__main__":
    unittest.main()
