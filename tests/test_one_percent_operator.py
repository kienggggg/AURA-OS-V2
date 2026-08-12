from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.one_percent_operator import OnePercentRevenueOperator


class OnePercentRevenueOperatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.product = self.root / "inventory" / "ocean_animals.pdf"
        self.product.parent.mkdir()
        self.product.write_bytes(b"%PDF-1.4 test")
        self.now_value = 1_784_880_000
        self.session_calls = 0
        self.publish_calls: list[tuple[Path, float, bool]] = []

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _operator(
        self, *, session_ok: bool = True, products: list[Path] | None = None
    ) -> OnePercentRevenueOperator:
        def session() -> dict:
            self.session_calls += 1
            return {"ok": session_ok, "reason": "session_active" if session_ok else "login_required"}

        def publish(pdf_file: Path, price: float, publish_now: bool) -> dict:
            self.publish_calls.append((pdf_file, price, publish_now))
            return {"success": True, "status": "published", "title": "Ocean Animals"}

        return OnePercentRevenueOperator(
            state_path=self.root / "operator.json",
            products_path=self.root / "products.jsonl",
            inventory=lambda: products or [self.product],
            session_checker=session,
            publisher=publish,
            now=lambda: self.now_value,
            price_usd=3.99,
            daily_publish_cap=1,
        )

    def test_no_network_or_publication_before_owner_confirmation(self) -> None:
        operator = self._operator()

        result = operator.run_once()

        self.assertEqual(result["outcome"], "waiting_for_owner_setup")
        self.assertEqual(self.session_calls, 0)
        self.assertEqual(self.publish_calls, [])
        self.assertFalse(operator.status()["autonomy_enabled"])

    def test_confirmation_publishes_one_unlisted_original_product_and_records_audit(self) -> None:
        operator = self._operator()
        operator.activate_after_owner_setup()

        first = operator.run_once()
        second = operator.run_once()
        state = operator.status()

        self.assertEqual(first["outcome"], "published")
        self.assertEqual(second["outcome"], "inventory_exhausted")
        self.assertEqual(len(self.publish_calls), 1)
        self.assertEqual(self.publish_calls[0], (self.product, 3.99, True))
        self.assertEqual(state["published_total"], 1)
        self.assertEqual(state["remaining_products"], 0)
        self.assertIn("product_published", [item["event"] for item in state["history"]])

    def test_invalid_payhip_session_never_calls_publisher(self) -> None:
        operator = self._operator(session_ok=False)
        operator.activate_after_owner_setup()

        result = operator.run_once()

        self.assertEqual(result["outcome"], "payhip_session_unavailable")
        self.assertEqual(len(self.publish_calls), 0)
        self.assertEqual(operator.status()["stage"], "needs_payhip_session")

    def test_daily_cap_leaves_other_original_products_for_the_next_day(self) -> None:
        second_product = self.product.parent / "forest_animals.pdf"
        second_product.write_bytes(b"%PDF-1.4 test two")
        operator = self._operator(products=[self.product, second_product])
        operator.activate_after_owner_setup()

        first = operator.run_once()
        second = operator.run_once()

        self.assertEqual(first["outcome"], "published")
        self.assertEqual(second["outcome"], "daily_publish_cap_reached")
        self.assertEqual(len(self.publish_calls), 1)
        self.assertEqual(operator.status()["remaining_products"], 1)

    def test_dashboard_exposes_read_only_one_percent_status(self) -> None:
        from interface.dashboard import build_dashboard_app

        app = build_dashboard_app()
        resources = {route.resource.canonical for route in app.router.routes()}
        self.assertIn("/api/one-percent-revenue", resources)


if __name__ == "__main__":
    unittest.main()
