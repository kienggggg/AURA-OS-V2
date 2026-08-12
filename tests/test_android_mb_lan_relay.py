from __future__ import annotations

import unittest
from unittest.mock import patch

from core.android_mb_lan_relay import RelayInputError, ingest_payload


class AndroidMbLanRelayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.body = {
            "amount": 125000,
            "currency": "VND",
            "reference": "a" * 64,
            "received_at": 1_700_000_000,
        }

    def test_valid_token_creates_only_minimal_cashflow_event(self) -> None:
        captured: dict = {}

        def fake_capture(**kwargs):
            captured.update(kwargs)
            return {"id": "evt-1", "status": "observed"}

        with patch("core.android_mb_lan_relay.token_matches", return_value=True):
            result = ingest_payload(self.body, "pair-token", capture=fake_capture)

        self.assertEqual({"id": "evt-1", "status": "observed"}, result)
        self.assertEqual("mbbank_android_notification", captured["source"])
        self.assertEqual("MB Bank báo có từ Android", captured["description"])

    def test_bad_token_or_reference_is_rejected_before_cashflow(self) -> None:
        with patch("core.android_mb_lan_relay.token_matches", return_value=False):
            with self.assertRaises(RelayInputError) as denied:
                ingest_payload(self.body, "wrong")
        self.assertEqual(403, denied.exception.status)

        with patch("core.android_mb_lan_relay.token_matches", return_value=True):
            with self.assertRaises(RelayInputError):
                ingest_payload({**self.body, "reference": "not-a-hash"}, "pair-token")


if __name__ == "__main__":
    unittest.main()
