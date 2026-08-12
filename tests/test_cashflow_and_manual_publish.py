from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.cashflow import capture_incoming, confirm, list_events, summary
from core.manual_publish_desk import list_items, mark_done


class CashflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = self.root / "cashflow.jsonl"
        self.alerts: list[tuple[float, str]] = []
        self.notifications: list[str] = []

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_capture_is_idempotent_and_does_not_record_income_before_confirmation(self) -> None:
        first = capture_incoming(
            amount=250_000, currency="VND", source="bank_notification", reference="TX-001",
            description="Thanh toán đơn PDF", path=self.ledger,
            announcer=lambda amount, currency: self.alerts.append((amount, currency)),
            notifier=lambda event: self.notifications.append(event["id"]),
        )
        duplicate = capture_incoming(
            amount=250_000, currency="VND", source="bank_notification", reference="TX-001",
            description="Thanh toán đơn PDF", path=self.ledger,
            announcer=lambda amount, currency: self.alerts.append((amount, currency)),
            notifier=lambda event: self.notifications.append(event["id"]),
        )

        self.assertEqual(first["id"], duplicate["id"])
        self.assertEqual(self.alerts, [(250_000.0, "VND")])
        self.assertEqual(self.notifications, [first["id"]])
        self.assertEqual(len(list_events(path=self.ledger)), 1)
        self.assertEqual(summary(path=self.ledger)["pending_by_currency"], {"VND": 250_000.0})

    def test_only_owner_confirmation_writes_one_income_record(self) -> None:
        event = capture_incoming(
            amount=99_000, reference="TX-002", description="Đơn hàng", path=self.ledger,
            announcer=lambda *_: None, notifier=lambda _event: None,
        )
        records: list[dict] = []

        with self.assertRaises(ValueError):
            confirm(event["id"], confirmed_by_owner=False, path=self.ledger)
        confirmed = confirm(
            event["id"], confirmed_by_owner=True, product_line="payhip", path=self.ledger,
            income_recorder=lambda **kwargs: records.append(kwargs) or kwargs,
        )
        again = confirm(
            event["id"], confirmed_by_owner=True, path=self.ledger,
            income_recorder=lambda **kwargs: records.append(kwargs) or kwargs,
        )

        self.assertEqual(confirmed["status"], "confirmed")
        self.assertEqual(again["id"], event["id"])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["amount"], 99_000.0)


class ManualPublishDeskTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.outputs = self.root / "outputs"
        self.pdf = self.outputs / "coloringbook" / "book-a" / "Forest Friends.pdf"
        self.pdf.parent.mkdir(parents=True)
        self.pdf.write_bytes(b"%PDF-1.4 test")
        self.actions = self.root / "manual_actions.jsonl"
        self.youtube = self.root / "publishes.jsonl"
        self.payhip = self.root / "payhip_products.jsonl"
        self.one_percent = self.root / "one_percent.json"
        self.youtube.write_text(json.dumps({
            "ts": 1_784_880_000, "platform": "youtube", "privacy": "private", "video_id": "video-1",
            "title": "Video cần công khai", "file": str(self.outputs / "story_video" / "video.mp4"),
        }) + "\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _items(self) -> list[dict]:
        return list_items(
            actions_path=self.actions, youtube_publishes_path=self.youtube,
            payhip_products_path=self.payhip, one_percent_state_path=self.one_percent,
            outputs_dir=self.outputs,
        )

    def test_desk_collects_private_youtube_and_payhip_pdf_with_safe_links(self) -> None:
        items = self._items()

        self.assertEqual({item["platform"] for item in items}, {"YouTube", "Payhip"})
        youtube = next(item for item in items if item["platform"] == "YouTube")
        payhip = next(item for item in items if item["platform"] == "Payhip")
        self.assertIn("studio.youtube.com", youtube["publish_url"])
        self.assertEqual(payhip["artifact_url"], "/files/outputs/coloringbook/book-a/Forest%20Friends.pdf")

    def test_marking_done_removes_only_that_manual_item(self) -> None:
        youtube = next(item for item in self._items() if item["platform"] == "YouTube")
        done = mark_done(
            youtube["id"], confirmed_by_owner=True, actions_path=self.actions,
            youtube_publishes_path=self.youtube, payhip_products_path=self.payhip,
            one_percent_state_path=self.one_percent, outputs_dir=self.outputs,
        )

        self.assertEqual(done["status"], "completed_by_owner")
        self.assertEqual([item["platform"] for item in self._items()], ["Payhip"])

    def test_active_one_percent_operator_hides_payhip_to_prevent_duplicate_publication(self) -> None:
        self.one_percent.write_text(json.dumps({
            "owner_payout_confirmed": True, "autonomy_enabled": True,
        }), encoding="utf-8")

        items = self._items()

        self.assertEqual([item["platform"] for item in items], ["YouTube"])

    def test_dashboard_exposes_cashflow_and_manual_publish_routes(self) -> None:
        from interface.dashboard import build_dashboard_app

        app = build_dashboard_app()
        resources = {route.resource.canonical for route in app.router.routes()}
        self.assertIn("/api/cashflow", resources)
        self.assertIn("/api/cashflow/incoming", resources)
        self.assertIn("/api/cashflow/{event_id}/confirm", resources)
        self.assertIn("/api/manual-publish", resources)
        self.assertIn("/api/manual-publish/{item_id}/done", resources)


if __name__ == "__main__":
    unittest.main()
