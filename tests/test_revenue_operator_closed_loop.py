"""Closed-loop tests for the autonomous but owner-gated Revenue Operator."""

from __future__ import annotations

import asyncio
import inspect
import json
import time
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from core.config import settings
from core.daemon import AuraDaemon
from core.lead_collector import (
    ACTIVE_NICHE,
    collect_verified_leads,
    stable_lead_id,
)
from core.market_test import evaluate_market_metrics
from core.revenue_operator import (
    confirm_proposal_sent,
    run_revenue_operator_cycle,
    run_revenue_operator_cycle_if_due,
)
from core.revenue_pipeline import get_pipeline_summary, update_pipeline_status
from interface.dashboard import build_dashboard_app


def _lead(url: str = "https://jobs.acme.test/python-automation-123") -> dict:
    return {
        "title": "Python automation developer",
        "url": url,
        "source": "Public Jobs Feed",
        "niche": ACTIVE_NICHE,
        "requirement": "Build a Python automation script and data pipeline.",
        "contact_channel": f"Apply at {url}",
        "budget_signal": "Budget shown on source",
        "source_posted_at": "2026-07-25T00:00:00Z",
    }


def _write_cohort(path: Path, experiment_id: str) -> None:
    path.write_text(
        json.dumps(
            {
                "experiment_id": experiment_id,
                "started_at": int(time.time()) - 5,
                "active_niche": ACTIVE_NICHE,
            }
        ),
        encoding="utf-8",
    )


def _empty_action_sources(tmp_path: Path) -> dict:
    paths = {
        "actions_path": tmp_path / "manual_actions.jsonl",
        "youtube_publishes_path": tmp_path / "youtube.jsonl",
        "payhip_products_path": tmp_path / "payhip.jsonl",
        "one_percent_state_path": tmp_path / "one_percent.json",
        "outputs_dir": tmp_path / "outputs",
    }
    paths["youtube_publishes_path"].write_text("", encoding="utf-8")
    paths["payhip_products_path"].write_text("", encoding="utf-8")
    paths["outputs_dir"].mkdir()
    return paths


def test_stable_lead_id_deduplicates_across_batches(tmp_path, monkeypatch):
    source = {
        "name": "Test",
        "url": "https://feed.example.net/jobs",
        "type": "rss",
        "niche": ACTIVE_NICHE,
    }
    monkeypatch.setattr("core.lead_collector.LIVE_FEED_SOURCES", [source])
    monkeypatch.setattr(
        "core.lead_collector.fetch_live_leads_from_rss",
        lambda _feed: [_lead("https://jobs.acme.test/123?utm_source=one")],
    )

    first = collect_verified_leads(
        experiment_id="EXP-STABLE",
        verify_http=False,
        file_path=tmp_path / "batch_one.json",
    )
    second = collect_verified_leads(
        experiment_id="EXP-STABLE",
        verify_http=False,
        file_path=tmp_path / "batch_two.json",
    )

    assert first[0]["collection_batch_id"] != second[0]["collection_batch_id"]
    assert first[0]["id"] == second[0]["id"]
    assert first[0]["id"] == stable_lead_id("https://jobs.acme.test/123")


def test_blank_experiment_events_never_count(tmp_path, monkeypatch):
    cohort_path = tmp_path / "cohort.json"
    leads_path = tmp_path / "leads.json"
    pipeline_path = tmp_path / "pipeline.jsonl"
    _write_cohort(cohort_path, "EXP-CURRENT")
    leads_path.write_text("[]", encoding="utf-8")
    pipeline_path.write_text(
        json.dumps(
            {
                "ts": int(time.time()),
                "experiment_id": "",
                "lead_id": "LEAD-BLANK",
                "status": "pitched",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("core.market_test._COHORT_FILE", cohort_path)
    metrics = evaluate_market_metrics(
        file_path=pipeline_path,
        leads_path=leads_path,
    )
    assert metrics["ever_pitched_14d"] == 0


def test_restart_safe_cycle_cooldown(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps({"status": "completed", "last_run_at": 100}),
        encoding="utf-8",
    )
    calls: list[dict] = []

    def fake_cycle(**kwargs):
        calls.append(kwargs)
        return {"status": "completed", "last_run_at": 201}

    monkeypatch.setattr("core.revenue_operator.run_revenue_operator_cycle", fake_cycle)
    skipped = run_revenue_operator_cycle_if_due(
        interval_seconds=100,
        now=150,
        state_path=state_path,
    )
    completed = run_revenue_operator_cycle_if_due(
        interval_seconds=100,
        now=201,
        state_path=state_path,
    )
    assert skipped["status"] == "skipped"
    assert skipped["next_run_at"] == 200
    assert completed["status"] == "completed"
    assert len(calls) == 1


def test_cycle_to_action_to_owner_confirmation_is_closed_loop(tmp_path, monkeypatch):
    experiment_id = "EXP-CLOSED-LOOP"
    cohort_path = tmp_path / "cohort.json"
    leads_path = tmp_path / "leads.json"
    pipeline_path = tmp_path / "pipeline.jsonl"
    state_path = tmp_path / "state.json"
    _write_cohort(cohort_path, experiment_id)
    monkeypatch.setattr("core.market_test._COHORT_FILE", cohort_path)
    monkeypatch.setattr(
        "core.lead_collector.LIVE_FEED_SOURCES",
        [{"name": "Test", "url": "https://feed.example.net", "type": "rss", "niche": ACTIVE_NICHE}],
    )
    monkeypatch.setattr(
        "core.lead_collector.fetch_live_leads_from_rss",
        lambda _feed: [_lead()],
    )
    monkeypatch.setattr(
        "core.revenue_operator._ensure_m8_package",
        lambda: {"success": True, "manifest": str(tmp_path / "manifest.json")},
    )

    report = run_revenue_operator_cycle(
        verify_http=False,
        pipeline_path=pipeline_path,
        leads_path=leads_path,
        state_path=state_path,
    )
    lead_id = report["new_qualified_ids"][0]
    assert get_pipeline_summary(experiment_id, pipeline_path)["qualified"] == 1

    with pytest.raises(PermissionError):
        confirm_proposal_sent(
            lead_id,
            confirmed_by_owner=False,
            pipeline_path=pipeline_path,
            leads_path=leads_path,
        )
    confirm_proposal_sent(
        lead_id,
        confirmed_by_owner=True,
        pipeline_path=pipeline_path,
        leads_path=leads_path,
    )
    summary = get_pipeline_summary(experiment_id, pipeline_path)
    metrics = evaluate_market_metrics(
        file_path=pipeline_path,
        leads_path=leads_path,
    )
    assert summary["pitched"] == 1
    assert metrics["ever_pitched_14d"] == 1


def test_action_box_priority_timestamp_and_local_link(tmp_path):
    from core.cashflow import capture_incoming
    from core.manual_publish_desk import get_unified_action_box_items

    experiment_id = "EXP-ACTIONS"
    pipeline_path = tmp_path / "pipeline.jsonl"
    cashflow_path = tmp_path / "cashflow.jsonl"
    update_pipeline_status(
        "LEAD-ACTION",
        "Python automation",
        "qualified",
        experiment_id=experiment_id,
        url="https://jobs.acme.test/action",
        file_path=pipeline_path,
    )
    capture_incoming(
        amount=690_000,
        currency="VND",
        source="test",
        reference="REF-ACTION",
        path=cashflow_path,
        announcer=lambda *_args: None,
        notifier=lambda _event: None,
    )
    actions = get_unified_action_box_items(
        experiment_id=experiment_id,
        pipeline_path=pipeline_path,
        cashflow_path=cashflow_path,
        **_empty_action_sources(tmp_path),
    )
    assert [item["type"] for item in actions] == [
        "cashflow_confirmation",
        "proposal",
    ]
    assert actions[0]["created_at"] > 0
    assert (
        f":{settings.dashboard_port}/leads/LEAD-ACTION"
        in actions[1]["publish_url"]
    )


def test_dashboard_form_and_proposal_routes_end_to_end(tmp_path, monkeypatch):
    experiment_id = "EXP-HTTP"
    cohort_path = tmp_path / "cohort.json"
    leads_path = tmp_path / "leads.json"
    pipeline_path = tmp_path / "pipeline.jsonl"
    demo_dir = tmp_path / "demo"
    _write_cohort(cohort_path, experiment_id)
    monkeypatch.setattr("core.market_test._COHORT_FILE", cohort_path)
    monkeypatch.setattr("core.lead_collector._LEADS_FILE", leads_path)
    monkeypatch.setattr("core.revenue_pipeline._PIPELINE_FILE", pipeline_path)
    monkeypatch.setattr("core.growth_operator._DEMO_DIR", demo_dir)

    now = int(time.time())
    lead = {
        **_lead(),
        "id": "LEAD-HTTP",
        "collection_batch_id": "BATCH-HTTP",
        "experiment_id": experiment_id,
        "verified_at": now,
        "collected_at": now,
    }
    leads_path.write_text(json.dumps([lead]), encoding="utf-8")
    update_pipeline_status(
        lead["id"],
        lead["title"],
        "qualified",
        experiment_id=experiment_id,
        url=lead["url"],
        contact_channel=lead["contact_channel"],
        file_path=pipeline_path,
    )

    async def scenario() -> None:
        client = TestClient(TestServer(build_dashboard_app()))
        await client.start_server()
        try:
            proposal = await client.get("/leads/LEAD-HTTP")
            assert proposal.status == 200
            assert "Tôi xác nhận đã gửi đề xuất" in await proposal.text()
            action_box = await client.get("/api/action-box")
            assert action_box.status == 200
            action_data = await action_box.json()
            assert any(
                item.get("type") == "proposal"
                and item.get("publish_url", "").endswith("/leads/LEAD-HTTP")
                for item in action_data["items"]
            )

            invalid = await client.post(
                "/api/demo_submit",
                json={"name": "A", "phone": "abc"},
            )
            assert invalid.status == 400
            accepted = await client.post(
                "/api/demo_submit",
                json={"name": "Nguyễn Văn A", "phone": "0987 654 321", "niche": "crawl"},
            )
            assert accepted.status == 201

            denied = await client.post(
                "/api/revenue-operator/leads/LEAD-HTTP/pitched",
                json={"confirmed_by_owner": False},
            )
            assert denied.status == 400
            pitched = await client.post(
                "/api/revenue-operator/leads/LEAD-HTTP/pitched",
                json={"confirmed_by_owner": True, "note": "Đã gửi thủ công"},
            )
            assert pitched.status == 200
        finally:
            await client.close()

    asyncio.run(scenario())
    assert len((demo_dir / "submissions.jsonl").read_text(encoding="utf-8").splitlines()) == 1
    assert get_pipeline_summary(experiment_id, pipeline_path)["pitched"] == 1


def test_daemon_registers_revenue_operator_heartbeat():
    start_source = inspect.getsource(AuraDaemon.start)
    heartbeat_source = inspect.getsource(AuraDaemon._revenue_operator_heartbeat)
    assert "_revenue_operator_heartbeat()" in start_source
    assert "run_revenue_operator_cycle_if_due" in heartbeat_source
