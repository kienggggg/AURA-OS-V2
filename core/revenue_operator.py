"""
Safe, closed-loop Revenue Operator for AURA.

The operator may collect public leads and prepare local sales material. It never
sends a proposal or marks revenue by itself: the owner confirms the proposal,
and payment state still comes from the confirmed cashflow ledger.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from core.config import PROJECT_ROOT
from core.lead_collector import (
    ACTIVE_NICHE,
    collect_verified_leads,
    get_current_verified_leads,
)
from core.market_test import evaluate_market_metrics, get_or_create_experiment_cohort
from core.revenue_pipeline import (
    _read_all_pipeline_events,
    get_current_lead_state,
    get_lead_snapshot,
    get_pipeline_summary,
    update_pipeline_status,
)

logger = logging.getLogger("aura.revenue_operator")
_CYCLE_LOCK = threading.RLock()
_CYCLE_STATE_FILE = PROJECT_ROOT / "data" / "ledger" / "operator_cycle_state.json"


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        dir=path.parent,
        delete=False,
        encoding="utf-8",
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        temp_name = handle.name
    os.replace(temp_name, path)


def read_cycle_state(state_path: Path | None = None) -> dict[str, Any]:
    path = state_path or _CYCLE_STATE_FILE
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _existing_package_is_ready() -> dict[str, Any] | None:
    """Return a valid local package result without rendering the same kit again."""
    try:
        from core import growth_operator

        manifest_path = growth_operator._DEMO_DIR / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, list) or len(artifacts) < 5:
            return None
        captions_are_current = False
        for item in artifacts:
            artifact_path = Path(str(item.get("path") or ""))
            if not artifact_path.is_file() or artifact_path.stat().st_size <= 0:
                return None
            expected_size = int(item.get("size_bytes") or 0)
            if expected_size and artifact_path.stat().st_size != expected_size:
                return None
            if artifact_path.name == "demo_7_captions.md":
                captions = artifact_path.read_text(encoding="utf-8")
                captions_are_current = (
                    "đây chưa phải cam kết doanh thu" in captions
                    and "1.000 sản phẩm chỉ trong 2 phút" not in captions
                )
        if not captions_are_current:
            return None
        return {
            "success": True,
            "manifest": str(manifest_path),
            "video_count": int(manifest.get("video_count") or 0),
            "caption_count": int(manifest.get("caption_count") or 0),
            "reused": True,
        }
    except (OSError, ValueError, TypeError):
        return None


def _ensure_m8_package() -> dict[str, Any]:
    existing = _existing_package_is_ready()
    if existing:
        return existing
    from core.growth_operator import execute_m8_package

    return execute_m8_package()


def run_revenue_operator_cycle(
    *,
    niche: str = ACTIVE_NICHE,
    target_count: int = 20,
    verify_http: bool = True,
    pipeline_path: Path | None = None,
    leads_path: Path | None = None,
    state_path: Path | None = None,
) -> dict[str, Any]:
    """Run one safe local cycle and persist an auditable state snapshot."""
    with _CYCLE_LOCK:
        started_at = int(time.time())
        cohort = get_or_create_experiment_cohort()
        experiment_id = str(cohort.get("experiment_id") or "").strip()
        if not experiment_id:
            raise ValueError("Revenue Operator không thể chạy khi thiếu experiment_id.")

        collected_leads = collect_verified_leads(
            niche=niche,
            target_count=target_count,
            verify_http=verify_http,
            experiment_id=experiment_id,
            file_path=leads_path,
        )

        existing_events = _read_all_pipeline_events(pipeline_path)
        existing_keys = {
            (str(event.get("experiment_id") or ""), str(event.get("lead_id") or ""))
            for event in existing_events
            if event.get("lead_id")
        }

        added_ids: list[str] = []
        errors: list[dict[str, str]] = []
        for lead in collected_leads:
            lead_id = str(lead.get("id") or "").strip()
            if not lead_id or (experiment_id, lead_id) in existing_keys:
                continue
            try:
                update_pipeline_status(
                    lead_id=lead_id,
                    title=str(lead.get("title") or "Lead mới"),
                    status="qualified",
                    notes=(
                        "AURA chuẩn bị cục bộ từ batch "
                        f"{lead.get('collection_batch_id')}; chưa gửi ra ngoài."
                    ),
                    experiment_id=experiment_id,
                    url=str(lead.get("url") or ""),
                    contact_channel=str(lead.get("contact_channel") or ""),
                    file_path=pipeline_path,
                )
                added_ids.append(lead_id)
                existing_keys.add((experiment_id, lead_id))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Không thể thêm lead %s vào pipeline: %s", lead_id, exc)
                errors.append({"lead_id": lead_id, "error": str(exc)})

        package = _ensure_m8_package()
        metrics = evaluate_market_metrics(
            file_path=pipeline_path,
            leads_path=leads_path,
        )
        completed_at = int(time.time())
        state = {
            "status": "completed",
            "last_run_at": completed_at,
            "started_at": started_at,
            "experiment_id": experiment_id,
            "niche": niche,
            "leads_collected": len(collected_leads),
            "new_qualified_added": len(added_ids),
            "new_qualified_ids": added_ids,
            "package_success": bool(package.get("success")),
            "package_manifest": str(package.get("manifest") or ""),
            "package_reused": bool(package.get("reused")),
            "checkpoint_14d_status": metrics.get("checkpoint_14d_status"),
            "errors": errors,
        }
        _atomic_write_json(state_path or _CYCLE_STATE_FILE, state)
        logger.info(
            "Revenue Operator hoàn tất: %d lead, %d qualified mới.",
            len(collected_leads),
            len(added_ids),
        )
        return state


def run_revenue_operator_cycle_if_due(
    *,
    interval_seconds: float,
    force: bool = False,
    now: int | None = None,
    state_path: Path | None = None,
    **cycle_kwargs: Any,
) -> dict[str, Any]:
    """Apply a restart-safe cooldown before running the production cycle."""
    interval_seconds = float(interval_seconds)
    if interval_seconds <= 0:
        raise ValueError("interval_seconds phải lớn hơn 0.")
    with _CYCLE_LOCK:
        check_time = int(now if now is not None else time.time())
        previous = read_cycle_state(state_path)
        last_run_at = int(previous.get("last_run_at") or 0)
        next_run_at = last_run_at + int(interval_seconds) if last_run_at else check_time
        if not force and last_run_at and check_time < next_run_at:
            return {
                "status": "skipped",
                "reason": "not_due",
                "last_run_at": last_run_at,
                "next_run_at": next_run_at,
                "seconds_until_next_run": next_run_at - check_time,
            }
        return run_revenue_operator_cycle(state_path=state_path, **cycle_kwargs)


def get_proposal_context(
    lead_id: str,
    *,
    pipeline_path: Path | None = None,
    leads_path: Path | None = None,
) -> dict[str, Any] | None:
    """Resolve one proposal against the active experiment only."""
    cohort = get_or_create_experiment_cohort()
    experiment_id = str(cohort.get("experiment_id") or "").strip()
    if not experiment_id:
        return None

    snapshot = get_lead_snapshot(lead_id, experiment_id, pipeline_path)
    leads, _ = get_current_verified_leads(
        expected_experiment_id=experiment_id,
        file_path=leads_path,
    )
    live_lead = next(
        (item for item in leads if str(item.get("id") or "") == lead_id),
        None,
    )
    if not snapshot and not live_lead:
        return None
    merged = dict(snapshot or {})
    for key, value in (live_lead or {}).items():
        if value not in (None, ""):
            merged[key] = value
    merged["experiment_id"] = experiment_id
    merged["lead_id"] = lead_id
    merged["status"] = get_current_lead_state(lead_id, experiment_id, pipeline_path)
    return merged


def confirm_proposal_sent(
    lead_id: str,
    *,
    confirmed_by_owner: bool,
    note: str = "",
    pipeline_path: Path | None = None,
    leads_path: Path | None = None,
) -> dict[str, Any]:
    """Record an owner's real send action; this function never submits externally."""
    if not confirmed_by_owner:
        raise PermissionError("Chỉ Chủ AURA mới được xác nhận đề xuất đã gửi.")
    context = get_proposal_context(
        lead_id,
        pipeline_path=pipeline_path,
        leads_path=leads_path,
    )
    if not context:
        raise LookupError("Không tìm thấy lead trong experiment hiện hành.")
    if context.get("status") != "qualified":
        raise ValueError(
            f"Lead phải ở trạng thái qualified, hiện tại là {context.get('status')!r}."
        )
    return update_pipeline_status(
        lead_id=lead_id,
        title=str(context.get("title") or "Lead"),
        status="pitched",
        notes=("Chủ xác nhận đã gửi đề xuất. " + str(note or "").strip()).strip(),
        experiment_id=str(context["experiment_id"]),
        url=str(context.get("url") or ""),
        contact_channel=str(context.get("contact_channel") or ""),
        file_path=pipeline_path,
    )


def get_revenue_operator_dashboard_data(
    *,
    pipeline_path: Path | None = None,
    leads_path: Path | None = None,
    state_path: Path | None = None,
) -> dict[str, Any]:
    cohort = get_or_create_experiment_cohort()
    experiment_id = str(cohort.get("experiment_id") or "").strip()
    leads, batch_id = get_current_verified_leads(
        expected_experiment_id=experiment_id,
        file_path=leads_path,
    )
    return {
        "cohort": cohort,
        "batch_id": batch_id,
        "leads": leads,
        "pipeline": get_pipeline_summary(experiment_id, pipeline_path),
        "last_cycle": read_cycle_state(state_path),
    }


__all__ = [
    "confirm_proposal_sent",
    "get_proposal_context",
    "get_revenue_operator_dashboard_data",
    "read_cycle_state",
    "run_revenue_operator_cycle",
    "run_revenue_operator_cycle_if_due",
]
