from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.work_for_hire import create_draft, next_actions, summary, transition


class WorkForHirePipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = self.root / "work_for_hire.jsonl"
        self.artifact = self.root / "proposal.md"
        self.artifact.write_text("# Proposal", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_verified_high_fit_draft_requires_owner_approval(self) -> None:
        deal = create_draft(
            title="Python automation",
            url="https://example.com/jobs/123",
            fit_score=90,
            artifact=str(self.artifact),
            source_verified=True,
            path=self.ledger,
        )
        self.assertEqual(deal["status"], "needs_owner_approval")
        self.assertEqual(next_actions(path=self.ledger)[0]["id"], deal["id"])

    def test_cannot_claim_submission_without_owner_confirmation(self) -> None:
        deal = create_draft(
            title="Python automation",
            url="https://example.com/jobs/123",
            fit_score=90,
            artifact=str(self.artifact),
            source_verified=True,
            path=self.ledger,
        )
        transition(deal["id"], "approved_to_submit", path=self.ledger)
        with self.assertRaises(ValueError):
            transition(deal["id"], "submitted", path=self.ledger)

    def test_owner_can_add_a_verified_source_to_a_manual_draft(self) -> None:
        deal = create_draft(
            title="Data cleanup",
            fit_score=85,
            artifact=str(self.artifact),
            path=self.ledger,
        )
        self.assertEqual(deal["status"], "needs_source")
        updated = transition(
            deal["id"], "needs_owner_approval", confirmed_by_owner=True,
            url="https://example.com/jobs/data-cleanup", path=self.ledger,
        )
        self.assertTrue(updated["source_verified"])
        self.assertEqual(updated["status"], "needs_owner_approval")

    def test_paid_requires_positive_confirmed_amount_and_updates_summary(self) -> None:
        deal = create_draft(
            title="Python automation",
            url="https://example.com/jobs/123",
            fit_score=90,
            artifact=str(self.artifact),
            source_verified=True,
            path=self.ledger,
        )
        for state, confirmed in (
            ("approved_to_submit", False),
            ("submitted", True),
            ("won", False),
            ("delivering", False),
            ("delivered", False),
            ("invoiced", False),
        ):
            transition(deal["id"], state, confirmed_by_owner=confirmed, path=self.ledger)
        with self.assertRaises(ValueError):
            transition(deal["id"], "paid", confirmed_by_owner=True, amount=0, path=self.ledger)
        transition(
            deal["id"], "paid", confirmed_by_owner=True,
            amount=750_000, currency="VND", path=self.ledger,
        )
        self.assertEqual(summary(path=self.ledger)["paid_by_currency"], {"VND": 750_000.0})

    def test_dashboard_exposes_pipeline_routes(self) -> None:
        from interface.dashboard import build_dashboard_app

        app = build_dashboard_app()
        resources = {route.resource.canonical for route in app.router.routes()}
        self.assertIn("/api/work-for-hire", resources)
        self.assertIn("/api/work-for-hire/{deal_id}/status", resources)


if __name__ == "__main__":
    unittest.main()
