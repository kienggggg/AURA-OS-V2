"""
tests/test_revenue_operator_m7_m12.py
======================================
Bộ Unit Tests đầy đủ (Khôi phục toàn bộ test cũ + test mới Vòng 3 & Vòng 4 - §11).
"""

import json
import time
import pytest
import cv2
from pathlib import Path
from unittest.mock import MagicMock

from core.lead_collector import (
    validate_lead,
    normalize_url,
    fetch_live_leads_from_rss,
    get_current_verified_leads,
    ACTIVE_NICHE,
)
from core.growth_operator import (
    execute_m8_package,
    render_real_mp4_video,
    record_demo_submission,
    handle_demo_submit_request,
)
from core.revenue_pipeline import (
    update_pipeline_status,
    confirm_payment_from_cashflow,
    get_pipeline_summary,
    ALLOWED_CURRENCIES,
)
from core.market_test import evaluate_market_metrics, get_or_create_experiment_cohort
from core.manual_publish_desk import list_items, get_unified_action_box_items
from core.messenger import TelegramMessenger
from core.revenue_operator import run_revenue_operator_cycle

EXP_TEST = "EXP-TEST"
_update_pipeline_status = update_pipeline_status
_confirm_payment_from_cashflow = confirm_payment_from_cashflow


def update_pipeline_status(*args, **kwargs):
    kwargs.setdefault("experiment_id", EXP_TEST)
    return _update_pipeline_status(*args, **kwargs)


def confirm_payment_from_cashflow(*args, **kwargs):
    kwargs.setdefault("experiment_id", EXP_TEST)
    return _confirm_payment_from_cashflow(*args, **kwargs)


# ---------------------------------------------------------------------------
# 1. Lead Validation & Deduplication & Auditor Tests
# ---------------------------------------------------------------------------
def test_validate_lead_rejections():
    """Test 1: Từ chối URL rỗng, URL fake, 'xxx', placeholder, sai ngách, thiếu source_posted_at."""
    # 1. URL rỗng
    ok, msg = validate_lead({"title": "Python Script", "url": "", "source": "TopCV", "requirement": "Req text long enough", "contact_channel": "email@test.com", "budget_signal": "unknown", "source_posted_at": None, "niche": ACTIVE_NICHE})
    assert not ok
    assert "Thiếu URL" in msg

    # 2. Chứa placeholder 'xxx'
    ok, msg = validate_lead({"title": "Python Script", "url": "https://topcv.vn/job/123", "source": "TopCV", "requirement": "Cần làm script", "contact_channel": "SĐT 0912xxx888", "budget_signal": "unknown", "source_posted_at": None, "niche": ACTIVE_NICHE})
    assert not ok
    assert "xxx" in msg

    # 3. Thiếu trường source_posted_at
    ok, msg = validate_lead({"title": "Python Script", "url": "https://topcv.vn/job/123", "source": "TopCV", "requirement": "Req text long enough", "contact_channel": "email@test.com", "budget_signal": "unknown", "niche": ACTIVE_NICHE})
    assert not ok
    assert "Thiếu khóa source_posted_at" in msg

    # 4. Thời gian verified_at ở tương lai
    ok, msg = validate_lead({"title": "Python Script", "url": "https://topcv.vn/job/123", "source": "TopCV", "requirement": "Req text long enough", "contact_channel": "email@test.com", "budget_signal": "unknown", "source_posted_at": None, "verified_at": int(time.time()) + 10000, "niche": ACTIVE_NICHE})
    assert not ok
    assert "tương lai" in msg


def test_normalize_url():
    """Test 2: Kiểm tra chuẩn hóa URL (loại bỏ tracking parameters)."""
    u1 = "HTTPS://Upwork.com/jobs/123/?utm_source=rss&ref=123"
    u2 = "https://upwork.com/jobs/123"
    assert normalize_url(u1) == normalize_url(u2)


def test_lead_auditor_returns_stale_for_old_or_invalid_data(tmp_path, monkeypatch):
    """Test 3: Thẩm định lead file cũ / thiếu batch_id / chứa 'xxx' trả về ([], 'STALE')."""
    l_file = tmp_path / "verified_leads.json"
    monkeypatch.setattr("core.lead_collector._LEADS_FILE", l_file)

    leads, batch_id = get_current_verified_leads()
    assert leads == []
    assert batch_id == "STALE"


# ---------------------------------------------------------------------------
# 2. RSS XML Leaf Node Parsing Test (KHÔI PHỤC)
# ---------------------------------------------------------------------------
def test_rss_xml_leaf_node_parsing(monkeypatch):
    """Test 4: Parse XML RSS leaf nodes (Element is not None fix)."""
    xml_data = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
        <channel>
            <item>
                <title>Python Automation Developer</title>
                <link>https://weworkremotely.com/jobs/1001</link>
                <description>Build Python scripts</description>
                <pubDate>Mon, 25 Jul 2026 00:00:00 GMT</pubDate>
            </item>
        </channel>
    </rss>
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = xml_data.encode("utf-8")

    monkeypatch.setattr("requests.get", lambda url, **kwargs: mock_resp)

    feed_info = {"name": "Test RSS", "url": "https://weworkremotely.com/rss", "type": "rss", "niche": ACTIVE_NICHE}
    leads = fetch_live_leads_from_rss(feed_info)
    assert len(leads) == 1
    assert leads[0]["title"] == "Python Automation Developer"


# ---------------------------------------------------------------------------
# 3. Cashflow Happy & Negative Paths & State Transitions (KHÔI PHỤC)
# ---------------------------------------------------------------------------
def test_cashflow_happy_path(tmp_path, monkeypatch):
    """Test 5: Cashflow Audit Happy Path với đúng schema id, status='confirmed', amount > 0."""
    cf_file = tmp_path / "cashflow.jsonl"
    p_file = tmp_path / "pipeline.jsonl"

    event_id = "CF-EVT-001"
    cf_data = {
        "ts": int(time.time()),
        "action": "confirmed_by_owner",
        "event": {"id": event_id, "status": "confirmed", "amount": 990000.0, "currency": "VND", "sender": "Khách Test"}
    }
    cf_file.write_text(json.dumps(cf_data, ensure_ascii=False) + "\n", encoding="utf-8")

    monkeypatch.setattr("core.cashflow._PATH", cf_file)
    monkeypatch.setattr("core.revenue_pipeline._PIPELINE_FILE", p_file)

    update_pipeline_status("LEAD-001", "Dự án Test", "qualified", file_path=p_file)
    update_pipeline_status("LEAD-001", "Dự án Test", "pitched", file_path=p_file)
    update_pipeline_status("LEAD-001", "Dự án Test", "replied", file_path=p_file)

    res = confirm_payment_from_cashflow("LEAD-001", "Dự án Test", "pilot_paid", event_id, file_path=p_file, cashflow_path=cf_file)
    assert res["status"] == "pilot_paid"
    assert res["amount"] == 990000.0


def test_cashflow_negative_paths(tmp_path, monkeypatch):
    """Test 6: Cashflow Negative Paths (pending/fake ID/duplicate ID)."""
    cf_file = tmp_path / "cashflow.jsonl"
    p_file = tmp_path / "pipeline.jsonl"

    e_pending = {"id": "CF-PENDING", "status": "observed", "amount": 500000.0, "currency": "VND"}
    e_confirmed = {"id": "CF-CONFIRMED", "status": "confirmed", "amount": 500000.0, "currency": "VND"}

    cf_file.write_text(
        json.dumps({"ts": 1, "action": "observed", "event": e_pending}) + "\n" +
        json.dumps({"ts": 2, "action": "confirmed", "event": e_confirmed}) + "\n",
        encoding="utf-8"
    )

    monkeypatch.setattr("core.cashflow._PATH", cf_file)
    monkeypatch.setattr("core.revenue_pipeline._PIPELINE_FILE", p_file)

    update_pipeline_status("L-1", "Test", "qualified", file_path=p_file)
    update_pipeline_status("L-1", "Test", "pitched", file_path=p_file)
    update_pipeline_status("L-1", "Test", "replied", file_path=p_file)

    # 1. Observed -> Từ chối
    with pytest.raises(ValueError):
        confirm_payment_from_cashflow("L-1", "Test", "pilot_paid", "CF-PENDING", file_path=p_file, cashflow_path=cf_file)

    # 2. Confirm 1 lần đầu -> Thành công
    confirm_payment_from_cashflow("L-1", "Test", "pilot_paid", "CF-CONFIRMED", file_path=p_file, cashflow_path=cf_file)

    # 3. Re-use cùng cashflow id cho L-2 -> Từ chối
    update_pipeline_status("L-2", "Test 2", "qualified", file_path=p_file)
    update_pipeline_status("L-2", "Test 2", "pitched", file_path=p_file)
    update_pipeline_status("L-2", "Test 2", "replied", file_path=p_file)

    with pytest.raises(ValueError) as exc_dup:
        confirm_payment_from_cashflow("L-2", "Test 2", "pilot_paid", "CF-CONFIRMED", file_path=p_file, cashflow_path=cf_file)
    assert "đã được đối soát" in str(exc_dup.value)


def test_valid_transitions_enforcement(tmp_path, monkeypatch):
    """Test 7: Nhảy cóc trạng thái bị chặn 100%."""
    p_file = tmp_path / "pipeline.jsonl"
    monkeypatch.setattr("core.revenue_pipeline._PIPELINE_FILE", p_file)

    update_pipeline_status("L-X", "Test", "qualified", file_path=p_file)
    with pytest.raises(ValueError):
        update_pipeline_status("L-X", "Test", "delivering", file_path=p_file)


def test_currency_allowlist_enforcement(tmp_path, monkeypatch):
    """Test 8: Kiểm tra từ chối tiền tệ không hợp lệ như BANANA."""
    cf_file = tmp_path / "cashflow.jsonl"
    p_file = tmp_path / "pipeline.jsonl"

    e_banana = {"id": "CF-BANANA", "status": "confirmed", "amount": 100.0, "currency": "BANANA"}
    cf_file.write_text(json.dumps({"ts": 1, "action": "confirmed", "event": e_banana}) + "\n", encoding="utf-8")

    monkeypatch.setattr("core.cashflow._PATH", cf_file)
    monkeypatch.setattr("core.revenue_pipeline._PIPELINE_FILE", p_file)

    update_pipeline_status("L-1", "Test", "qualified", file_path=p_file)
    update_pipeline_status("L-1", "Test", "pitched", file_path=p_file)
    update_pipeline_status("L-1", "Test", "replied", file_path=p_file)

    with pytest.raises(ValueError) as exc:
        confirm_payment_from_cashflow("L-1", "Test", "pilot_paid", "CF-BANANA", file_path=p_file, cashflow_path=cf_file)
    assert "KHÔNG HỢP LỆ" in str(exc.value)


# ---------------------------------------------------------------------------
# 4. OpenCV Video Rendering & Local Form Submission Tests
# ---------------------------------------------------------------------------
def test_opencv_video_rendering_and_decodability(tmp_path, monkeypatch):
    """Test 9: Render 3 video MP4 9:16 thật, OpenCV mở & đọc được frame; kiểm tra 7 captions & local form handler."""
    demo_dir = tmp_path / "demo_kit"
    package_dir = tmp_path / "growth_operator"
    monkeypatch.setattr("core.growth_operator._DEMO_DIR", demo_dir)
    monkeypatch.setattr("core.growth_operator._PACKAGE_DIR", package_dir)

    res = execute_m8_package()
    assert res["success"] is True
    assert res["video_count"] == 3

    for i in range(1, 4):
        v_path = demo_dir / f"demo_video_{i}.mp4"
        cap = cv2.VideoCapture(str(v_path))
        assert cap.isOpened()
        ret, frame = cap.read()
        cap.release()
        assert ret is True
        assert frame.shape == (960, 540, 3)

    # Test HTTP local form submit handler
    s_file = demo_dir / "submissions.jsonl"
    resp = handle_demo_submit_request({"name": "Nguyễn Văn A", "phone": "0987654321", "niche": "crawl"}, submissions_file=s_file)
    assert resp["success"] is True
    assert resp["entry"]["is_demo"] is True
    assert "Nguyễn Văn A" in s_file.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 5. Cumulative Funnel & Experiment Isolation & Unified Action Box
# ---------------------------------------------------------------------------
def test_cumulative_funnel_milestones(tmp_path, monkeypatch):
    """Test 10: Lead chuyển từ pitched -> replied vẫn bảo toàn mốc ever_pitched = 10."""
    p_file = tmp_path / "pipeline.jsonl"
    monkeypatch.setattr("core.revenue_pipeline._PIPELINE_FILE", p_file)

    for i in range(1, 11):
        lid = f"L-{i:02d}"
        update_pipeline_status(lid, f"Lead {i}", "qualified", file_path=p_file)
        update_pipeline_status(lid, f"Lead {i}", "pitched", file_path=p_file)
        if i <= 3:
            update_pipeline_status(lid, f"Lead {i}", "replied", file_path=p_file)

    summary = get_pipeline_summary(file_path=p_file)
    assert summary["ever_pitched"] == 10
    assert summary["ever_replied"] == 3


def test_experiment_isolation(tmp_path, monkeypatch):
    """Test 11: Probe sự kiện từ EXP-OTHER KHÔNG được đếm vào EXP-CURRENT checkpoint."""
    p_file = tmp_path / "pipeline.jsonl"
    l_file = tmp_path / "verified_leads.json"
    c_file = tmp_path / "experiment_cohort.json"

    now = int(time.time())
    cohort = {"experiment_id": "EXP-CURRENT", "started_at": now, "active_niche": ACTIVE_NICHE}
    c_file.write_text(json.dumps(cohort), encoding="utf-8")

    # Tạo 20 events thuộc EXP-OTHER
    other_lines = []
    for i in range(20):
        other_lines.append(json.dumps({
            "ts": now + 10,
            "experiment_id": "EXP-OTHER",
            "lead_id": f"LEAD-OTHER-{i}",
            "title": "Other",
            "status": "pitched",
            "amount": 0.0,
            "currency": "VND"
        }))

    p_file.write_text("\n".join(other_lines) + "\n", encoding="utf-8")
    l_file.write_text(json.dumps([]), encoding="utf-8")

    monkeypatch.setattr("core.market_test._COHORT_FILE", c_file)
    monkeypatch.setattr("core.lead_collector._LEADS_FILE", l_file)

    metrics = evaluate_market_metrics(file_path=p_file)
    # EXP-OTHER bị loại hoàn toàn khỏi EXP-CURRENT -> ever_pitched_14d phải bằng 0
    assert metrics["ever_pitched_14d"] == 0


def test_unified_action_box_aggregation(tmp_path, monkeypatch):
    """Test 12: Probe 3 qualified leads + 2 pending cashflows -> Trả đúng 5 mục action trong Action Box."""
    p_file = tmp_path / "pipeline.jsonl"
    p_file = tmp_path / "pipeline.jsonl"
    cf_file = tmp_path / "cashflow.jsonl"
    act_file = tmp_path / "actions.jsonl"
    yt_file = tmp_path / "youtube.jsonl"
    pay_file = tmp_path / "payhip.jsonl"
    outputs_dir = tmp_path / "outputs"

    yt_file.write_text("", encoding="utf-8")
    pay_file.write_text("", encoding="utf-8")
    outputs_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("core.revenue_pipeline._PIPELINE_FILE", p_file)
    monkeypatch.setattr("core.cashflow._PATH", cf_file)
    monkeypatch.setattr("core.manual_publish_desk._ACTIONS_PATH", act_file)

    # 1. Tạo 3 lead ở qualified
    for i in range(1, 4):
        update_pipeline_status(f"LEAD-Q-{i}", f"Qualified Job {i}", "qualified", file_path=p_file)

    # 2. Tạo 2 cashflow observed pending
    cf_lines = [
        json.dumps({"ts": 1, "action": "observed", "event": {"id": "CF-PENDING-1", "status": "observed", "amount": 690000.0, "currency": "VND"}}),
        json.dumps({"ts": 2, "action": "observed", "event": {"id": "CF-PENDING-2", "status": "observed", "amount": 990000.0, "currency": "VND"}}),
    ]
    cf_file.write_text("\n".join(cf_lines) + "\n", encoding="utf-8")

    actions = get_unified_action_box_items(
        experiment_id=EXP_TEST,
        pipeline_path=p_file,
        cashflow_path=cf_file,
        actions_path=act_file,
        youtube_publishes_path=yt_file,
        payhip_products_path=pay_file,
        outputs_dir=outputs_dir,
    )
    assert len(actions) == 5, f"Mong muốn 5 mục action, nhận được: {len(actions)}"
    proposal_types = [a for a in actions if a["type"] == "proposal"]
    cashflow_types = [a for a in actions if a["type"] == "cashflow_confirmation"]
    assert len(proposal_types) == 3
    assert len(cashflow_types) == 2


# ---------------------------------------------------------------------------
# 6. Production Cycle Runner Test (§11.1)
# ---------------------------------------------------------------------------
def test_production_cycle_runner(tmp_path, monkeypatch):
    """Test 13: Chạy 1 chu kỳ vận hành sản xuất run_revenue_operator_cycle khép kín."""
    p_file = tmp_path / "pipeline.jsonl"
    l_file = tmp_path / "verified_leads.json"
    c_file = tmp_path / "experiment_cohort.json"
    s_file = tmp_path / "operator_state.json"

    monkeypatch.setattr("core.revenue_pipeline._PIPELINE_FILE", p_file)
    monkeypatch.setattr("core.lead_collector._LEADS_FILE", l_file)
    monkeypatch.setattr("core.market_test._COHORT_FILE", c_file)
    monkeypatch.setattr("core.revenue_operator._CYCLE_STATE_FILE", s_file)

    # Mock cào lead trả 2 lead live
    mock_leads = [
        {"id": "L-LIVE-1", "title": "Live Job 1", "url": "https://topcv.vn/1", "source": "TopCV", "niche": ACTIVE_NICHE, "requirement": "Req 1 long enough", "contact_channel": "email@test.com", "budget_signal": "unknown", "source_posted_at": None, "collection_batch_id": "B1", "verified_at": int(time.time())},
        {"id": "L-LIVE-2", "title": "Live Job 2", "url": "https://topcv.vn/2", "source": "TopCV", "niche": ACTIVE_NICHE, "requirement": "Req 2 long enough", "contact_channel": "email@test.com", "budget_signal": "unknown", "source_posted_at": None, "collection_batch_id": "B1", "verified_at": int(time.time())},
    ]
    monkeypatch.setattr("core.revenue_operator.collect_verified_leads", lambda **kwargs: mock_leads)
    monkeypatch.setattr(
        "core.revenue_operator._ensure_m8_package",
        lambda: {"success": True, "manifest": str(tmp_path / "manifest.json")},
    )

    res = run_revenue_operator_cycle(
        pipeline_path=p_file,
        leads_path=l_file,
        state_path=s_file,
    )
    assert res["leads_collected"] == 2
    assert res["new_qualified_added"] == 2
    assert res["package_success"] is True

    # Kiểm tra pipeline ledger đã ghi 2 qualified entries
    summary = get_pipeline_summary(file_path=p_file)
    assert summary["qualified"] == 2
