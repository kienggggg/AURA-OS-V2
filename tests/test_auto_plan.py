from __future__ import annotations

import unittest

from core.vibe_diff import VibeDiffInterceptor, auto_plan_approvals


class AutoPlanTests(unittest.TestCase):
    def test_local_draft_and_research_tools_are_auto_approved(self) -> None:
        gate = VibeDiffInterceptor(auto_approve=auto_plan_approvals(True))
        self.assertTrue(gate.intercept("freelance.apply", {"job_url": "https://example.com/job"})[0])
        self.assertTrue(gate.intercept("story.factory", {"series": "draft"})[0])
        self.assertTrue(gate.intercept("job.scout", {"keywords": "python"})[0])

    def test_external_or_destructive_tools_stay_blocked(self) -> None:
        gate = VibeDiffInterceptor(auto_approve=auto_plan_approvals(True))
        self.assertFalse(gate.intercept("youtube.upload", {"title": "public"})[0])
        self.assertFalse(gate.intercept("system.control", {"action": "delete", "target": "x"})[0])

    def test_switch_off_restores_no_explicit_auto_approvals(self) -> None:
        self.assertFalse(auto_plan_approvals(False))


if __name__ == "__main__":
    unittest.main()
