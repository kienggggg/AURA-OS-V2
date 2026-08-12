"""
core/manual_publish_desk.py
===========================
BÀN ĐĂNG TAY: GOM NỘI DUNG AURA ĐÃ CHUẨN BỊ (CÓ CAPTION SIDECAR & CHUẨN XÁC NGUYÊN TẮC §9.5)
========================================================================================
- Gom những nội dung AURA đã chuẩn bị nhưng Chủ cần tự công khai.
- YouTube Private: Đưa link Studio để Chủ tự đổi Public.
- Payhip PDF: Đưa link Payhip để Chủ đăng.
- Facebook Page: Trạng thái BLOCKED API -> Cung cấp bài viết + caption sidecar để Chủ tự dán.
- TikTok Video: Mô tả trung thực "File AURA đã chuẩn bị, Chủ cần tự upload", đính kèm file caption sidecar.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

from core.config import settings

logger = logging.getLogger("aura.manual_publish_desk")
_ACTIONS_PATH = settings.ledger_dir / "manual_publish_actions.jsonl"
_YOUTUBE_PUBLISHES_PATH = settings.ledger_dir / "publishes.jsonl"
_PAYHIP_PRODUCTS_PATH = settings.ledger_dir / "payhip_products.jsonl"
_ONE_PERCENT_STATE_PATH = settings.ledger_dir / "one_percent_operator.json"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return rows
    for line in lines:
        try:
            row = json.loads(line)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _item_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _output_url(path: Path, outputs_dir: Path) -> str:
    try:
        relative = path.resolve().relative_to(outputs_dir.resolve())
    except (OSError, ValueError):
        return ""
    return "/files/outputs/" + "/".join(quote(part) for part in relative.parts)


def _done_ids(actions_path: Path) -> set[str]:
    return {
        str(row.get("item_id") or "")
        for row in _read_jsonl(actions_path)
        if row.get("action") == "completed_by_owner" and row.get("item_id")
    }


def _one_percent_is_active(state_path: Path) -> bool:
    try:
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    except (OSError, ValueError, json.JSONDecodeError):
        state = {}
    return bool(state.get("owner_payout_confirmed") and state.get("autonomy_enabled"))


def list_items(
    *,
    actions_path: Path | None = None,
    youtube_publishes_path: Path | None = None,
    payhip_products_path: Path | None = None,
    one_percent_state_path: Path | None = None,
    outputs_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Liệt kê nội dung thực tế đang cần một thao tác công khai bằng tay."""
    actions = actions_path or _ACTIONS_PATH
    youtube_ledger = youtube_publishes_path or _YOUTUBE_PUBLISHES_PATH
    payhip_ledger = payhip_products_path or _PAYHIP_PRODUCTS_PATH
    one_percent_state = one_percent_state_path or _ONE_PERCENT_STATE_PATH
    outputs = outputs_dir or settings.outputs_dir
    done = _done_ids(actions)
    items: list[dict[str, Any]] = []

    # 1. YouTube PRIVATE
    for row in _read_jsonl(youtube_ledger):
        if str(row.get("platform") or "") != "youtube" or str(row.get("privacy") or "").lower() != "private":
            continue
        video_id = str(row.get("video_id") or "").strip()
        if not video_id:
            continue
        item_id = _item_id("youtube", video_id)
        if item_id in done:
            continue
        file_path = Path(str(row.get("file") or ""))
        items.append({
            "id": item_id,
            "platform": "YouTube",
            "title": str(row.get("title") or "Video riêng tư"),
            "action": "Mở Studio và đổi từ Riêng tư sang Công khai.",
            "artifact_url": _output_url(file_path, outputs),
            "caption_text": f"Tiêu đề: {row.get('title')}\nMô tả:\n{row.get('description', '')}",
            "publish_url": f"https://studio.youtube.com/video/{quote(video_id, safe='')}/edit",
            "created_at": int(row.get("ts") or 0),
        })

    # 2. Payhip PDF
    if not _one_percent_is_active(one_percent_state):
        published_keys = {
            str(row.get("product_key") or "")
            for row in _read_jsonl(payhip_ledger)
            if str(row.get("status") or "") == "published"
        }
        coloring_dir = outputs / "coloringbook"
        pdfs = sorted(coloring_dir.glob("*/*.pdf")) if coloring_dir.is_dir() else []
        if not pdfs and coloring_dir.is_dir():
            pdfs = sorted(coloring_dir.glob("*.pdf"))
        for pdf in pdfs:
            key = str(pdf.resolve()).casefold()
            if key in published_keys:
                continue
            item_id = _item_id("payhip", key)
            if item_id in done:
                continue
            items.append({
                "id": item_id,
                "platform": "Payhip",
                "title": pdf.stem.replace("_", " "),
                "action": "Mở Payhip, tải PDF AURA đã chuẩn bị và đăng sản phẩm.",
                "artifact_url": _output_url(pdf, outputs),
                "caption_text": f"Sản phẩm PDF: {pdf.name}",
                "publish_url": "https://payhip.com/dashboard/products/add",
                "created_at": int(pdf.stat().st_mtime),
            })

    # 3. Facebook Page (M11: Chờ Meta Developer API -> Đưa bài viết + caption để Chủ tự dán)
    fb_drafts_dir = outputs / "facebook_drafts"
    if fb_drafts_dir.is_dir():
        for txt in sorted(fb_drafts_dir.glob("*.txt")):
            item_id = _item_id("facebook", str(txt.resolve()))
            if item_id in done:
                continue
            caption = txt.read_text(encoding="utf-8", errors="replace") if txt.is_file() else ""
            items.append({
                "id": item_id,
                "platform": "Facebook Page",
                "title": txt.stem.replace("_", " "),
                "action": "Mở Facebook Page Business Suite và đăng bài viết AURA đã soạn.",
                "artifact_url": _output_url(txt, outputs),
                "caption_text": caption,
                "publish_url": "https://business.facebook.com/latest/composer",
                "created_at": int(txt.stat().st_mtime),
            })

    # 4. TikTok (M11: Mô tả trung thực "File AURA đã chuẩn bị, Chủ cần tự upload")
    tiktok_drafts_dir = outputs / "tiktok_drafts"
    if tiktok_drafts_dir.is_dir():
        for mp4 in sorted(tiktok_drafts_dir.glob("*.mp4")):
            item_id = _item_id("tiktok", str(mp4.resolve()))
            if item_id in done:
                continue
            caption_file = mp4.with_suffix(".txt")
            caption = caption_file.read_text(encoding="utf-8", errors="replace") if caption_file.is_file() else f"Video TikTok: {mp4.name}"
            items.append({
                "id": item_id,
                "platform": "TikTok",
                "title": mp4.stem.replace("_", " "),
                "action": "File AURA đã chuẩn bị, Chủ cần tự upload trên TikTok app/web.",
                "artifact_url": _output_url(mp4, outputs),
                "caption_text": caption,
                "publish_url": "https://www.tiktok.com/upload",
                "created_at": int(mp4.stat().st_mtime),
            })

    items.sort(key=lambda item: int(item.get("created_at") or 0), reverse=True)
    return items


def mark_done(
    item_id: str,
    *,
    confirmed_by_owner: bool,
    note: str = "",
    actions_path: Path | None = None,
    **sources: Any,
) -> dict[str, Any]:
    """Ghi audit sau khi Chủ đã tự đăng; không gọi bất kỳ nền tảng nào."""
    if not confirmed_by_owner:
        raise ValueError("Chỉ đánh dấu xong sau khi bạn đã tự công khai trên nền tảng.")
    actions = actions_path or _ACTIONS_PATH
    item = next((row for row in list_items(actions_path=actions, **sources) if row["id"] == str(item_id)), None)
    if item is None:
        raise KeyError("Không tìm thấy mục đang chờ đăng hoặc mục này đã được xử lý.")
    actions.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": int(time.time()),
        "action": "completed_by_owner",
        "item_id": item["id"],
        "platform": item["platform"],
        "title": item["title"],
        "note": " ".join(str(note or "").split())[:300],
    }
    with actions.open("a", encoding="utf-8") as file:
        file.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {**item, "status": "completed_by_owner"}


def dashboard_data() -> dict[str, Any]:
    items = list_items()
    by_platform: dict[str, int] = {}
    for item in items:
        platform = str(item.get("platform") or "Khác")
        by_platform[platform] = by_platform.get(platform, 0) + 1
    return {"summary": {"pending": len(items), "by_platform": by_platform}, "items": items}


def get_unified_action_box_items(
    *,
    experiment_id: str | None = None,
    pipeline_path: Path | None = None,
    cashflow_path: Path | None = None,
    actions_path: Path | None = None,
    **sources: Any,
) -> list[dict[str, Any]]:
    """Hợp nhất 100% 3 nguồn hành động 1% (Proposals, Manual Publish Desk, Cashflow Confirmations)."""
    actions: list[dict[str, Any]] = []
    if experiment_id is None:
        from core.market_test import get_or_create_experiment_cohort

        experiment_id = str(
            get_or_create_experiment_cohort().get("experiment_id") or ""
        ).strip()
    host = str(getattr(settings, "dashboard_host", "127.0.0.1") or "127.0.0.1")
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    dashboard_base = f"http://{host}:{int(settings.dashboard_port)}"

    # 1. Manual Publish Desk Items
    publish_items = list_items(actions_path=actions_path, **sources)
    for p in publish_items:
        actions.append({
            "id": p["id"],
            "type": "manual_publish",
            "platform": p.get("platform", "Đăng bài"),
            "title": p.get("title", ""),
            "action": p.get("action", ""),
            "artifact_url": p.get("artifact_url", ""),
            "publish_url": p.get("publish_url", ""),
            "created_at": int(p.get("created_at") or 0),
            "priority": 2,
        })

    # 2. Qualified Lead Proposals waiting for Pitch
    try:
        from core.revenue_pipeline import _read_all_pipeline_events
        events = _read_all_pipeline_events(pipeline_path)
        latest_lead_state: dict[str, dict] = {}
        for ev in events:
            lid = ev.get("lead_id")
            if lid and str(ev.get("experiment_id") or "") == experiment_id:
                latest_lead_state[lid] = ev

        for lid, ev in latest_lead_state.items():
            if ev.get("status") == "qualified":
                actions.append({
                    "id": f"action_proposal_{lid}",
                    "type": "proposal",
                    "platform": "Gửi Pitch Proposal",
                    "title": f"Gửi Pitch cho Lead {lid} ({ev.get('title', '')[:30]})",
                    "action": "Mở thông tin liên hệ và gửi bản chào hàng Gói thử 7 ngày AURA Growth Operator",
                    "artifact_url": "/files/outputs/growth_operator/chao_ban_aura_growth_operator.md",
                    "publish_url": f"{dashboard_base}/leads/{quote(str(lid), safe='')}",
                    "created_at": int(ev.get("ts") or 0),
                    "priority": 1,
                })
    except Exception as exc:  # noqa: BLE001
        logger.warning("Không thể đọc proposal actions: %s", exc)

    # 3. Cashflow Confirmations (status == "observed")
    try:
        from core.cashflow import _read as read_cashflow
        cf_rows = read_cashflow(cashflow_path)
        for cid, ev in cf_rows.items():
            if str(ev.get("status") or "") == "observed":
                amt = float(ev.get("amount") or 0.0)
                curr = str(ev.get("currency") or "VND").upper()
                actions.append({
                    "id": f"action_cf_{cid}",
                    "type": "cashflow_confirmation",
                    "platform": "MB Bank Báo Có",
                    "title": f"Xác nhận báo có {amt:,.0f} {curr} (ID: {cid})",
                    "action": "Đối soát báo có trên Desktop để chính thức công nhận doanh thu",
                    "artifact_url": "",
                    "publish_url": f"{dashboard_base}/#cashflow",
                    "created_at": int(
                        ev.get("updated_at")
                        or ev.get("received_at")
                        or ev.get("created_at")
                        or 0
                    ),
                    "priority": 0,
                })
    except Exception as exc:  # noqa: BLE001
        logger.warning("Không thể đọc cashflow actions: %s", exc)

    actions.sort(
        key=lambda action: (
            int(action.get("priority") or 0),
            -int(action.get("created_at") or 0),
        )
    )
    return actions


__all__ = ["dashboard_data", "list_items", "mark_done", "get_unified_action_box_items"]
