"""
interface/dashboard.py
=======================
Dashboard web local của Xưởng Kiếm Tiền — bảng điều khiển chính để SẾP TỰ DÙNG
mọi tool (không chỉ AURA tự chạy). Một file aiohttp (đã có sẵn trong venv,
KHÔNG cần FastAPI) + static HTML/JS đơn giản (interface/web/).

Chạy CÙNG event loop với WebSocket server (8765, kênh mascot) nhưng là server
HTTP riêng ở cổng khác (8766) — hai kênh độc lập, không tranh nhau.

Chỉ bind 127.0.0.1 — TUYỆT ĐỐI không mở ra mạng ngoài (không xác thực).
"""

from __future__ import annotations

import asyncio
import html
import hmac
import ipaddress
import logging
from pathlib import Path
from urllib.parse import quote

from aiohttp import web

from core.config import PROJECT_ROOT, settings
from factory import queue as job_queue
from factory.models import JobRecord
from factory.tools import get_tool, list_tools

logger = logging.getLogger("aura.interface.dashboard")

_WEB_DIR = Path(__file__).resolve().parent / "web"
_OUTPUTS_DIR = settings.outputs_dir


async def _request_payload(request: web.Request) -> dict:
    """Read JSON or a normal HTML form into the same small dictionary."""
    if request.content_type == "application/json":
        body = await request.json()
        return body if isinstance(body, dict) else {}
    form = await request.post()
    return dict(form)


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


async def _index(_request: web.Request) -> web.Response:
    return web.FileResponse(_WEB_DIR / "index.html")


async def _api_tools(_request: web.Request) -> web.Response:
    return web.json_response([t.to_dict() for t in list_tools()])


async def _api_jobs_list(request: web.Request) -> web.Response:
    state = request.query.get("state") or None
    limit = int(request.query.get("limit", "50"))
    jobs = job_queue.list_jobs(state=state, limit=limit)
    return web.json_response([j.to_dict() for j in jobs])


async def _api_jobs_create(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 — JSON hỏng -> lỗi rõ ràng, không sập server
        return web.json_response({"error": "Body không phải JSON hợp lệ."}, status=400)

    tool_name = str(body.get("tool") or "")
    params = body.get("params") or {}
    spec = get_tool(tool_name)
    if spec is None:
        return web.json_response({"error": f"Không có tool '{tool_name}'."}, status=404)
    if not spec.enabled:
        return web.json_response({"error": f"Tool '{tool_name}' chưa mở (đợt sau)."}, status=400)

    job = JobRecord(tool=tool_name, params=params)
    job_queue.enqueue(job)
    logger.info("Dashboard enqueue job %s (%s).", job.id, tool_name)
    return web.json_response(job.to_dict(), status=201)


async def _api_job_get(request: web.Request) -> web.Response:
    job_id = request.match_info["job_id"]
    job = job_queue.get(job_id)
    if job is None:
        return web.json_response({"error": "Không thấy job."}, status=404)
    return web.json_response(job.to_dict())


async def _api_job_cancel(request: web.Request) -> web.Response:
    job_id = request.match_info["job_id"]
    ok = job_queue.cancel(job_id)
    if not ok:
        return web.json_response({"error": "Không hủy được (đã xong/không tồn tại)."}, status=400)
    return web.json_response({"ok": True})


async def _api_job_qc(request: web.Request) -> web.Response:
    """Đọc qc_report.json của một job cho tab QC/nút xem chi tiết."""
    import json as _json
    job = job_queue.get(request.match_info["job_id"])
    if job is None or not job.qc_path or not Path(job.qc_path).exists():
        return web.json_response({"error": "Chưa có báo cáo QC."}, status=404)
    return web.json_response(_json.loads(Path(job.qc_path).read_text(encoding="utf-8")))


async def _api_ledger_get(request: web.Request) -> web.Response:
    from factory import ledger
    month = request.query.get("month") or None
    return web.json_response({
        "summary": ledger.monthly_summary(month),
        "entries": ledger.entries(limit=100),
    })


async def _api_ledger_post(request: web.Request) -> web.Response:
    from factory import ledger
    try:
        body = await request.json()
        row = ledger.record(
            product_line=str(body.get("product_line") or "khac"),
            item=str(body.get("item") or ""),
            amount=float(body.get("amount") or 0),
            direction=str(body.get("direction") or "in"),
            note=str(body.get("note") or ""),
        )
    except (ValueError, TypeError) as exc:
        return web.json_response({"error": f"Dữ liệu không hợp lệ: {exc}"}, status=400)
    return web.json_response(row, status=201)


async def _api_cashflow_get(_request: web.Request) -> web.Response:
    from core.cashflow import dashboard_data
    return web.json_response(dashboard_data())


async def _api_cashflow_incoming(request: web.Request) -> web.Response:
    """Cổng cho cầu nối thông báo ngân hàng cục bộ; luôn cần secret riêng."""
    secret = settings.cashflow_ingest_token
    expected = secret.get_secret_value() if secret else ""
    supplied = request.headers.get("X-AURA-Cashflow-Token", "")
    if expected:
        authenticated = hmac.compare_digest(supplied, expected)
    else:
        # Android bridge đi qua adb reverse tới localhost; token được sinh cục bộ, không cần
        # nhét secret vào .env hoặc đưa token Telegram/ngân hàng cho APK.
        from core.android_mb_pairing import token_matches
        authenticated = token_matches(supplied)
    if not authenticated:
        return web.json_response({"error": "Cầu nối báo có chưa được xác thực."}, status=403)
    try:
        body = await request.json()
        reference = str(body.get("reference") or "").strip()
        if not reference:
            raise ValueError("Báo có tự động cần mã giao dịch/reference để chống ghi trùng.")
        from core.cashflow import capture_incoming
        event = capture_incoming(
            amount=body.get("amount"),
            currency=str(body.get("currency") or "VND"),
            source=str(body.get("source") or "mbbank_push"),
            reference=reference,
            description=str(body.get("description") or "Báo có ngân hàng"),
            received_at=body.get("received_at"),
        )
    except (ValueError, TypeError) as exc:
        return web.json_response({"error": str(exc)}, status=400)
    return web.json_response(event, status=201)


async def _api_cashflow_confirm(request: web.Request) -> web.Response:
    try:
        body = await request.json()
        from core.cashflow import confirm
        event = confirm(
            request.match_info["event_id"],
            confirmed_by_owner=bool(body.get("confirmed_by_owner", False)),
            product_line=str(body.get("product_line") or "khac"),
            note=str(body.get("note") or ""),
        )
    except (ValueError, KeyError, TypeError) as exc:
        return web.json_response({"error": str(exc)}, status=400)
    return web.json_response(event)


async def _api_cashflow_ignore(request: web.Request) -> web.Response:
    try:
        body = await request.json()
        from core.cashflow import ignore
        event = ignore(
            request.match_info["event_id"],
            confirmed_by_owner=bool(body.get("confirmed_by_owner", False)),
        )
    except (ValueError, KeyError, TypeError) as exc:
        return web.json_response({"error": str(exc)}, status=400)
    return web.json_response(event)


async def _api_applications(_request: web.Request) -> web.Response:
    """Sổ rải CV — ưu tiên sổ chung của factory, vẫn đọc sổ cũ nếu còn."""
    import json as _json
    paths = [settings.ledger_dir / "applications.jsonl",
             PROJECT_ROOT / "data" / "feedback" / "applications.jsonl"]
    rows: list[dict] = []
    seen: set[tuple[str, str, int]] = set()
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = _json.loads(line)
            except _json.JSONDecodeError:
                continue
            key = (str(row.get("title") or ""), str(row.get("url") or ""), int(row.get("ts") or 0))
            if key not in seen:
                rows.append(row)
                seen.add(key)
    return web.json_response(rows[::-1][:100])


async def _api_work_for_hire(_request: web.Request) -> web.Response:
    """Pipeline nhận việc: chỉ dữ liệu/audit, không có chức năng gửi hồ sơ."""
    from core.work_for_hire import dashboard_data
    return web.json_response(dashboard_data())


async def _api_work_for_hire_status(request: web.Request) -> web.Response:
    """Ghi bước do Sếp xác nhận; tuyệt đối không gọi ra nền tảng tuyển dụng."""
    from core.work_for_hire import transition
    try:
        body = await request.json()
        deal = transition(
            request.match_info["deal_id"],
            str(body.get("status") or ""),
            confirmed_by_owner=bool(body.get("confirmed_by_owner", False)),
            url=str(body.get("url") or ""),
            amount=body.get("amount"),
            currency=str(body.get("currency") or "VND"),
            note=str(body.get("note") or ""),
        )
    except (ValueError, KeyError, TypeError) as exc:
        return web.json_response({"error": str(exc)}, status=400)
    return web.json_response(deal)


async def _api_one_percent_revenue(_request: web.Request) -> web.Response:
    """Trạng thái 1% Chủ / 99% AURA; chỉ đọc, không khởi chạy đăng sản phẩm."""
    from core.one_percent_operator import status
    return web.json_response(status())


async def _api_manual_publish_get(_request: web.Request) -> web.Response:
    from core.manual_publish_desk import dashboard_data
    return web.json_response(dashboard_data())


async def _api_manual_publish_done(request: web.Request) -> web.Response:
    try:
        body = await request.json()
        from core.manual_publish_desk import mark_done
        item = mark_done(
            request.match_info["item_id"],
            confirmed_by_owner=bool(body.get("confirmed_by_owner", False)),
            note=str(body.get("note") or ""),
        )
    except (ValueError, KeyError, TypeError) as exc:
        return web.json_response({"error": str(exc)}, status=400)
    return web.json_response(item)


async def _api_demo_submit(request: web.Request) -> web.Response:
    """Receive the local demo landing-page form; never forwards data externally."""
    try:
        body = await _request_payload(request)
        from core.growth_operator import handle_demo_submit_request

        result = handle_demo_submit_request(body)
    except (ValueError, TypeError, web.HTTPException) as exc:
        return web.json_response({"success": False, "error": str(exc)}, status=400)
    status = 201 if result.get("success") else 400
    if request.content_type == "application/json":
        return web.json_response(result, status=status)
    message = html.escape(str(result.get("message") or result.get("error") or ""))
    return web.Response(
        text=(
            "<!doctype html><html lang='vi'><meta charset='utf-8'>"
            "<title>AURA Demo</title><body style='font-family:sans-serif;max-width:680px;"
            "margin:60px auto'><h1>AURA Growth Operator</h1>"
            f"<p>{message}</p><p><a href='/'>Về bảng điều khiển</a></p></body></html>"
        ),
        content_type="text/html",
        status=status,
    )


async def _api_revenue_operator(_request: web.Request) -> web.Response:
    from core.revenue_operator import get_revenue_operator_dashboard_data

    return web.json_response(get_revenue_operator_dashboard_data())


async def _api_action_box(_request: web.Request) -> web.Response:
    """One desktop inbox for cashflow, proposals and manual-publication work."""
    from core.manual_publish_desk import get_unified_action_box_items

    items = get_unified_action_box_items()
    by_type: dict[str, int] = {}
    for item in items:
        item_type = str(item.get("type") or "other")
        by_type[item_type] = by_type.get(item_type, 0) + 1
    return web.json_response(
        {"summary": {"pending": len(items), "by_type": by_type}, "items": items}
    )


async def _api_desktop_autopilot(_request: web.Request) -> web.Response:
    """Return only safe desktop metadata; screenshots and raw OCR are never persisted."""
    from core.desktop_autopilot import get_runtime_autopilot

    return web.json_response(get_runtime_autopilot().status())


async def _api_desktop_autopilot_control(request: web.Request) -> web.Response:
    """One owner switch replaces per-click approval for pre-authorized local scopes."""
    try:
        body = await _request_payload(request)
        from core.desktop_autopilot import get_runtime_autopilot

        status = get_runtime_autopilot().set_control(
            str(body.get("action") or ""),
            confirmed_by_owner=_as_bool(body.get("confirmed_by_owner")),
        )
    except (PermissionError, ValueError, TypeError) as exc:
        return web.json_response({"error": str(exc)}, status=400)
    return web.json_response(status)


async def _api_desktop_autopilot_inspect(request: web.Request) -> web.Response:
    """Inspect the foreground window on demand without executing an action."""
    try:
        body = await _request_payload(request)
        include_ocr = _as_bool(body.get("include_ocr"))
        if include_ocr and not getattr(settings, "desktop_autopilot_ocr_enabled", True):
            raise ValueError("OCR local đang tắt trong cấu hình.")
        from core.desktop_autopilot import get_runtime_autopilot

        observation = await asyncio.to_thread(
            get_runtime_autopilot().observe,
            include_ocr=include_ocr,
        )
    except (ValueError, TypeError) as exc:
        return web.json_response({"error": str(exc)}, status=400)
    return web.json_response(observation)


async def _api_desktop_autopilot_context(request: web.Request) -> web.Response:
    """Summarize AURA's local self/memory connection without returning private text."""
    from core.desktop_autopilot import get_runtime_autopilot

    autopilot = get_runtime_autopilot()
    self_context = await asyncio.to_thread(autopilot.read_self_context)
    memory = await asyncio.to_thread(
        autopilot.recall_local_memory,
        str(request.query.get("query") or "AURA current task and owner preferences"),
    )
    return web.json_response(
        {
            "self": {
                "readable_file_count": len(self_context.get("files") or []),
                "source_file_count": self_context.get("source_file_count", 0),
                "recently_changed": self_context.get("recently_changed", []),
            },
            "memory": {
                "connected": bool(memory.get("available")),
                "record_count": len(memory.get("records") or []),
            },
            "private_text_exposed": False,
        }
    )


async def _api_revenue_operator_cycle(request: web.Request) -> web.Response:
    """Run a local preparation cycle on an explicit owner request."""
    try:
        body = await _request_payload(request)
        from core.revenue_operator import run_revenue_operator_cycle_if_due

        report = await asyncio.to_thread(
            run_revenue_operator_cycle_if_due,
            interval_seconds=(
                float(getattr(settings, "revenue_operator_interval_h", 24.0)) * 3600.0
            ),
            force=_as_bool(body.get("force")),
            target_count=int(getattr(settings, "revenue_operator_target_count", 20)),
        )
    except (ValueError, TypeError) as exc:
        return web.json_response({"error": str(exc)}, status=400)
    return web.json_response(report)


async def _lead_proposal_page(request: web.Request) -> web.Response:
    from core.revenue_operator import get_proposal_context

    lead_id = request.match_info["lead_id"]
    context = get_proposal_context(lead_id)
    if not context:
        raise web.HTTPNotFound(text="Không tìm thấy lead trong chiến dịch hiện hành.")
    title = html.escape(str(context.get("title") or lead_id))
    status = html.escape(str(context.get("status") or ""))
    source_url = str(context.get("url") or "").strip()
    source_link = (
        f"<a href='{html.escape(source_url, quote=True)}' target='_blank' rel='noopener'>"
        "Mở nguồn lead</a>"
        if source_url.startswith(("https://", "http://"))
        else "Nguồn lead chưa có URL hợp lệ"
    )
    contact = html.escape(str(context.get("contact_channel") or "Xem trên trang nguồn"))
    encoded_id = quote(lead_id, safe="")
    page = f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>AURA · Duyệt đề xuất</title>
<style>body{{font-family:system-ui;max-width:760px;margin:40px auto;padding:0 18px;
background:#0f172a;color:#e2e8f0}}.card{{background:#1e293b;padding:24px;border-radius:14px}}
a{{color:#38bdf8}}button{{padding:12px 18px;border:0;border-radius:8px;background:#16a34a;
color:white;font-weight:700;cursor:pointer}}textarea{{width:100%;min-height:90px;margin:10px 0 16px}}</style>
</head><body><div class="card"><p><a href="/">← Bảng điều khiển</a></p>
<h1>{title}</h1><p><b>Trạng thái:</b> {status}</p><p>{source_link}</p>
<p><b>Kênh liên hệ:</b> {contact}</p>
<p><a href="/files/outputs/growth_operator/chao_ban_aura_growth_operator.md">
Mở bản chào hàng AURA</a></p>
<p>AURA chỉ ghi nhận sau khi bạn đã tự gửi đề xuất trên trang nguồn.</p>
<form method="post" action="/api/revenue-operator/leads/{encoded_id}/pitched">
<input type="hidden" name="confirmed_by_owner" value="true">
<label>Ghi chú (không bắt buộc)</label><textarea name="note"></textarea>
<button type="submit">Tôi xác nhận đã gửi đề xuất</button></form></div></body></html>"""
    return web.Response(text=page, content_type="text/html")


async def _api_proposal_pitched(request: web.Request) -> web.Response:
    try:
        body = await _request_payload(request)
        from core.revenue_operator import confirm_proposal_sent

        event = confirm_proposal_sent(
            request.match_info["lead_id"],
            confirmed_by_owner=_as_bool(body.get("confirmed_by_owner")),
            note=str(body.get("note") or ""),
        )
    except (PermissionError, LookupError, ValueError, TypeError) as exc:
        return web.json_response({"error": str(exc)}, status=400)
    if request.content_type == "application/json":
        return web.json_response(event)
    return web.Response(
        text=(
            "<!doctype html><html lang='vi'><meta charset='utf-8'><title>AURA</title>"
            "<body style='font-family:sans-serif;max-width:680px;margin:60px auto'>"
            "<h1>Đã ghi nhận đề xuất đã gửi</h1><p>AURA đã chuyển lead sang pitched.</p>"
            "<p><a href='/'>Về bảng điều khiển</a></p></body></html>"
        ),
        content_type="text/html",
    )


async def _api_channels_get(_request: web.Request) -> web.Response:
    """Sổ kênh — mỗi kênh 1 ngách + nền tảng + loại nội dung + phong cách."""
    from factory import channels
    data = channels.all_channels()
    # Kênh nào đã có token YouTube (cấp quyền xong) -> đánh dấu để UI biết.
    yt_dir = PROJECT_ROOT / "data" / "youtube"
    for c in data:
        ytc = c.get("yt_channel") or c.get("key")
        c["authorized"] = (yt_dir / str(ytc) / "token.json").is_file()
    return web.json_response(data)


async def _api_channels_post(request: web.Request) -> web.Response:
    from factory import channels
    try:
        body = await request.json()
        saved = channels.upsert(body)
    except (ValueError, TypeError) as exc:
        return web.json_response({"error": f"Dữ liệu không hợp lệ: {exc}"}, status=400)
    return web.json_response(saved, status=201)


def build_dashboard_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", _index)
    app.router.add_get("/api/tools", _api_tools)
    app.router.add_get("/api/channels", _api_channels_get)
    app.router.add_post("/api/channels", _api_channels_post)
    app.router.add_get("/api/jobs", _api_jobs_list)
    app.router.add_post("/api/jobs", _api_jobs_create)
    app.router.add_get("/api/jobs/{job_id}", _api_job_get)
    app.router.add_post("/api/jobs/{job_id}/cancel", _api_job_cancel)
    app.router.add_get("/api/jobs/{job_id}/qc", _api_job_qc)
    app.router.add_get("/api/ledger/income", _api_ledger_get)
    app.router.add_post("/api/ledger/income", _api_ledger_post)
    app.router.add_get("/api/cashflow", _api_cashflow_get)
    app.router.add_post("/api/cashflow/incoming", _api_cashflow_incoming)
    app.router.add_post("/api/cashflow/{event_id}/confirm", _api_cashflow_confirm)
    app.router.add_post("/api/cashflow/{event_id}/ignore", _api_cashflow_ignore)
    app.router.add_get("/api/applications", _api_applications)
    app.router.add_get("/api/work-for-hire", _api_work_for_hire)
    app.router.add_post("/api/work-for-hire/{deal_id}/status", _api_work_for_hire_status)
    app.router.add_get("/api/one-percent-revenue", _api_one_percent_revenue)
    app.router.add_get("/api/manual-publish", _api_manual_publish_get)
    app.router.add_post("/api/manual-publish/{item_id}/done", _api_manual_publish_done)
    app.router.add_post("/api/demo_submit", _api_demo_submit)
    app.router.add_get("/api/revenue-operator", _api_revenue_operator)
    app.router.add_get("/api/action-box", _api_action_box)
    app.router.add_get("/api/desktop-autopilot", _api_desktop_autopilot)
    app.router.add_post("/api/desktop-autopilot/control", _api_desktop_autopilot_control)
    app.router.add_post("/api/desktop-autopilot/inspect", _api_desktop_autopilot_inspect)
    app.router.add_get("/api/desktop-autopilot/context", _api_desktop_autopilot_context)
    app.router.add_post("/api/revenue-operator/cycle", _api_revenue_operator_cycle)
    app.router.add_get("/leads/{lead_id}", _lead_proposal_page)
    app.router.add_post(
        "/api/revenue-operator/leads/{lead_id}/pitched",
        _api_proposal_pitched,
    )
    # Cửa TRƯỚC: màn hình chat. Trước 08/08/2026 bảng này có 28 cổng cho xưởng
    # kiếm tiền và không cổng nào để nói chuyện với AURA.
    #
    # 12/08/2026: AURA v3 tách sang repo riêng `D:\AURA_v3`, nên `interface.chat_api`
    # không còn ở đây nữa. Import này nằm TRONG hàm nên dashboard vẫn nạp được;
    # chỉ đường cắm chat là mất. Bắt hụt và đi tiếp thay vì để dashboard chết,
    # vì v2 giờ là kho phụ tùng — không ai chạy nó để chat nữa.
    try:
        from interface.chat_api import attach_chat_routes
    except ImportError:
        pass
    else:
        attach_chat_routes(app)
    # File thành phẩm để tải về (giới hạn CHỈ trong data/outputs/).
    app.router.add_static("/files/outputs/", path=str(_OUTPUTS_DIR), show_index=True)
    # HTML/CSS/JS tĩnh.
    app.router.add_static("/static/", path=str(_WEB_DIR), show_index=False)
    return app


def _is_loopback_host(host: str) -> bool:
    """Địa chỉ này có CHỈ nghe trên máy này không?

    Chấp nhận: rỗng (aiohttp -> localhost), 'localhost', và mọi IP loopback
    (127.0.0.0/8, ::1). TỪ CHỐI: '0.0.0.0'/'::' (wildcard = mọi card mạng) và
    mọi IP thật của máy.
    """
    candidate = (host or "").strip().strip("[]")
    if not candidate or candidate.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(candidate).is_loopback
    except ValueError:
        # Tên miền lạ -> không dám coi là an toàn.
        return False


def assert_dashboard_bind_safe(host: str, allow_lan: bool) -> None:
    """CHỐT CỨNG: chặn kịch bản 'đổi một dòng config là mở toang'.

    Dashboard có ~30 route KHÔNG xác thực (chỉ route nạp cashflow có token),
    trong đó có `/api/desktop-autopilot/control` — bật/tắt điều khiển CHUỘT và
    BÀN PHÍM thật. Thứ duy nhất che chúng là bind loopback. Đổi
    DASHBOARD_HOST=0.0.0.0 là cả mớ đó mở ra toàn mạng wifi, không hỏi mật khẩu.
    (Đúng cái bẫy đã dính với 9router: bind 0.0.0.0 làm lộ API key ra LAN.)

    Nên: host không phải loopback mà CHƯA bật cờ dashboard_allow_lan -> nổ ngay
    lúc khởi động, thay vì âm thầm mở cửa.
    """
    if _is_loopback_host(host):
        return
    if not allow_lan:
        raise RuntimeError(
            f"CHẶN: dashboard định bind '{host}' (không phải localhost) trong khi "
            "~30 route KHÔNG có xác thực — gồm cả route bật điều khiển chuột/bàn "
            "phím. Trả DASHBOARD_HOST về 127.0.0.1, hoặc đặt DASHBOARD_ALLOW_LAN=true "
            "nếu Sếp CỐ Ý mở ra mạng và chấp nhận rủi ro."
        )
    logger.warning(
        "⚠️ DASHBOARD MỞ RA MẠNG: đang bind '%s' với ~30 route KHÔNG xác thực "
        "(gồm /api/desktop-autopilot/control — điều khiển chuột/bàn phím). "
        "Bất kỳ ai cùng mạng đều dùng được. Chỉ làm vậy trên mạng nhà tin cậy.",
        host,
    )


async def start_dashboard() -> web.AppRunner:
    """Khởi động dashboard trên settings.dashboard_host:port, trả AppRunner để cleanup."""
    assert_dashboard_bind_safe(
        settings.dashboard_host, bool(getattr(settings, "dashboard_allow_lan", False))
    )
    app = build_dashboard_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, settings.dashboard_host, settings.dashboard_port)
    await site.start()
    logger.info(
        "Dashboard xưởng: http://%s:%d", settings.dashboard_host, settings.dashboard_port
    )
    return runner


__all__ = ["build_dashboard_app", "start_dashboard", "assert_dashboard_bind_safe"]
