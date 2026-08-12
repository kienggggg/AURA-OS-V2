from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.aura_avatar_bridge import configure_phone, pair_and_install
from core.aura_avatar_pairing import pairing, token_matches
from core.aura_avatar_relay import AvatarInputError, AvatarRelay, validate_payload
from core.orchestrator import AURA_Orchestrator
from core.schemas import IntentLabel, ToolResult


class AuraAvatarPairingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.state = self.root / "avatar-pairing.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_pairing_is_private_and_persistent(self) -> None:
        first = pairing(self.state)
        second = pairing(self.state)
        self.assertEqual(first, second)
        self.assertIn(":8768/v1/avatar/chat", first["endpoint"])
        self.assertTrue(token_matches(first["token"], self.state))
        self.assertFalse(token_matches("wrong", self.state))

    def test_install_uses_avatar_port_package_and_token(self) -> None:
        apk = self.root / "app-debug.apk"
        apk.write_bytes(b"placeholder")
        calls: list[list[str]] = []

        def runner(_adb: str, args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
            calls.append(args)
            stdout = "List of devices attached\nvivo-1\tdevice\n" if args == ["devices"] else "Success"
            return subprocess.CompletedProcess([_adb, *args], 0, stdout=stdout, stderr="")

        with patch("core.aura_avatar_bridge.pairing", return_value={
            "endpoint": "http://127.0.0.1:8768/v1/avatar/chat",
            "token": "avatar-token",
        }):
            message = pair_and_install(apk=apk, adb_path="adb", runner=runner)

        self.assertIn("AURA Avatar", message)
        self.assertIn(["-s", "vivo-1", "reverse", "tcp:8768", "tcp:8768"], calls)
        self.assertIn(["-s", "vivo-1", "install", "-r", str(apk)], calls)
        config = next(args for args in calls if args[:5] == ["-s", "vivo-1", "shell", "am", "start"])
        self.assertIn("vn.aura.avatar/.MainActivity", config)
        self.assertIn("avatar-token", config)

    def test_configure_rejects_non_avatar_route(self) -> None:
        def runner(_adb: str, args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
            stdout = "List of devices attached\nvivo-1\tdevice\n" if args == ["devices"] else "Success"
            return subprocess.CompletedProcess([_adb, *args], 0, stdout=stdout, stderr="")

        with self.assertRaises(ValueError):
            configure_phone(
                endpoint="http://127.0.0.1:8766/api/cashflow/incoming",
                adb_path="adb",
                runner=runner,
            )


class AuraAvatarRelayTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.body = {
            "device_id": "vivo_1904",
            "request_id": "request-0001",
            "text": "Xin chào AURA",
        }

    def test_validation_rejects_bad_token_and_oversized_text(self) -> None:
        with patch("core.aura_avatar_relay.token_matches", return_value=False):
            with self.assertRaises(AvatarInputError) as denied:
                validate_payload(self.body, "wrong")
        self.assertEqual(403, denied.exception.status)

        with patch("core.aura_avatar_relay.token_matches", return_value=True):
            with self.assertRaises(AvatarInputError) as oversized:
                validate_payload({**self.body, "text": "x" * 501}, "token")
        self.assertEqual(413, oversized.exception.status)

    async def test_replay_returns_cached_answer_without_second_brain_call(self) -> None:
        calls: list[str] = []

        async def responder(text: str) -> str:
            calls.append(text)
            return "Chào sếp, AURA đang nghe."

        relay = AvatarRelay(responder)
        with patch("core.aura_avatar_relay.token_matches", return_value=True):
            first, first_replay = await relay.chat(self.body, "token")
            second, second_replay = await relay.chat(self.body, "token")

        self.assertEqual(first, second)
        self.assertFalse(first_replay)
        self.assertTrue(second_replay)
        self.assertEqual(["Xin chào AURA"], calls)

    async def test_rate_limit_blocks_immediate_new_request(self) -> None:
        async def responder(_text: str) -> str:
            return "ok"

        relay = AvatarRelay(responder)
        with patch("core.aura_avatar_relay.token_matches", return_value=True):
            await relay.chat(self.body, "token")
            with self.assertRaises(AvatarInputError) as limited:
                await relay.chat({**self.body, "request_id": "request-0002"}, "token")
        self.assertEqual(429, limited.exception.status)


class _Memory:
    def recall_preferences(self, _text):
        return []

    def recall_rules(self, _text):
        return []

    def recall_knowledge(self, _text):
        return []

    def recall_context(self, _text):
        return []

    def query(self, *args, **kwargs):
        return []

    def remember_turn(self, *args, **kwargs):
        return None


class _Router:
    def __init__(self) -> None:
        self.intent = None
        self.system_prompt = ""

    def run(self, messages, intent, system_prompt=None, **kwargs):
        self.intent = intent
        self.system_prompt = system_prompt or ""
        return ToolResult.success("brain:test", "Tôi đang nghe đây.")


class AuraAvatarOrchestratorTests(unittest.TestCase):
    def test_avatar_is_conversation_only_and_cannot_consume_pending_control(self) -> None:
        router = _Router()
        orchestrator = AURA_Orchestrator(router=router, memory=_Memory())
        orchestrator.profile = None
        orchestrator._pending_control = "freeze"

        response = orchestrator.process_avatar_message("Y")

        self.assertEqual("Tôi đang nghe đây.", response)
        self.assertEqual("freeze", orchestrator._pending_control)
        self.assertEqual(IntentLabel.CHITCHAT, router.intent.label)
        self.assertIn("CHỈ HỘI THOẠI", router.system_prompt)
        self.assertIn("không duyệt", router.system_prompt)

    def test_avatar_reads_self_history_without_calling_router(self) -> None:
        router = _Router()
        orchestrator = AURA_Orchestrator(router=router, memory=_Memory())
        orchestrator.profile = None

        with patch(
            "core.orchestrator.answer_self_history",
            return_value="🩺 SỔ MỔ: Codex đang sửa hồ sơ.",
        ):
            response = orchestrator.process_avatar_message(
                "AURA, bạn có biết Claude, ChatGPT, Antigravity "
                "đã thay đổi những thứ gì của bạn không"
            )

        self.assertIn("SỔ MỔ", response)
        self.assertIsNone(router.intent)

    def test_avatar_reads_verified_lessons_without_calling_router(self) -> None:
        router = _Router()
        orchestrator = AURA_Orchestrator(router=router, memory=_Memory())
        orchestrator.profile = None

        with patch(
            "core.orchestrator.answer_self_tuition",
            return_value="🎓 GIÁO TRÌNH: tôi đã học cách đọc cơ thể mình.",
        ):
            response = orchestrator.process_avatar_message(
                "AURA đã học được gì về cơ thể mình?"
            )

        self.assertIn("GIÁO TRÌNH", response)
        self.assertIsNone(router.intent)

    def test_avatar_prompt_contains_verified_tuition_context(self) -> None:
        router = _Router()
        orchestrator = AURA_Orchestrator(router=router, memory=_Memory())
        orchestrator.profile = None

        with patch(
            "core.orchestrator.tuition_context",
            return_value="[GIÁO TRÌNH KIỂM CHỨNG TEST]",
        ):
            orchestrator.process_avatar_message("Xin chào AURA")

        self.assertIn("GIÁO TRÌNH KIỂM CHỨNG TEST", router.system_prompt)


if __name__ == "__main__":
    unittest.main()
