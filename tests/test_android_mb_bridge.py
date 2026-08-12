from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.android_mb_pairing import pairing, token_matches
from core.android_mb_bridge import configure_phone, pair_and_install


class AndroidMbPairingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.state = self.root / "pairing.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_pairing_persists_one_random_token(self) -> None:
        first = pairing(self.state)
        second = pairing(self.state)

        self.assertEqual(first, second)
        self.assertTrue(first["endpoint"].startswith("http://127.0.0.1:"))
        self.assertTrue(token_matches(first["token"], self.state))
        self.assertFalse(token_matches("not-the-token", self.state))

    def test_pair_and_install_uses_local_adb_reverse_then_passes_pairing_by_intent(self) -> None:
        apk = self.root / "app-debug.apk"
        apk.write_bytes(b"placeholder")
        calls: list[list[str]] = []

        def runner(_adb: str, args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
            calls.append(args)
            stdout = "List of devices attached\nphone-1\tdevice\n" if args == ["devices"] else "Success"
            return subprocess.CompletedProcess([_adb, *args], 0, stdout=stdout, stderr="")

        with patch("core.android_mb_bridge.pairing", return_value={
            "endpoint": "http://127.0.0.1:8766/api/cashflow/incoming", "token": "pair-token",
        }):
            message = pair_and_install(apk=apk, adb_path="adb", runner=runner)

        self.assertIn("Đã cài và ghép", message)
        self.assertIn(["-s", "phone-1", "reverse", "tcp:8766", "tcp:8766"], calls)
        self.assertIn(["-s", "phone-1", "install", "-r", str(apk)], calls)
        config = next(args for args in calls if args[:5] == ["-s", "phone-1", "shell", "am", "start"])
        self.assertIn("aura_token", config)
        self.assertIn("pair-token", config)

    def test_configure_phone_can_switch_an_existing_bridge_to_lan(self) -> None:
        calls: list[list[str]] = []

        def runner(_adb: str, args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
            calls.append(args)
            stdout = "List of devices attached\nphone-1\tdevice\n" if args == ["devices"] else "Success"
            return subprocess.CompletedProcess([_adb, *args], 0, stdout=stdout, stderr="")

        with patch("core.android_mb_bridge.pairing", return_value={
            "endpoint": "http://127.0.0.1:8766/api/cashflow/incoming", "token": "pair-token",
        }):
            configure_phone(
                endpoint="http://192.168.1.20:8767/v1/mbbank/incoming",
                adb_path="adb",
                runner=runner,
            )

        self.assertFalse(any("install" in call or "reverse" in call for call in calls))
        config = next(args for args in calls if args[:5] == ["-s", "phone-1", "shell", "am", "start"])
        self.assertIn("http://192.168.1.20:8767/v1/mbbank/incoming", config)


if __name__ == "__main__":
    unittest.main()
