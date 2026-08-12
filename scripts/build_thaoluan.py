# -*- coding: utf-8 -*-
"""Dựng phòng thảo luận Codex <-> Claude từ các lượt bất biến.

Mỗi người chỉ tạo một tệp lượt mới trong ``thaoluan/``.  Tệp HTML ở gốc là
khung nhìn được sinh lại, không phải nguồn dữ liệu và tuyệt đối không sửa tay.

Tên tệp bắt buộc::

    001-codex.html
    002-claude.html
    003-codex.html
    ...

Manifest SHA-256 làm cho việc sửa/xóa lời cũ bị phát hiện thay vì âm thầm làm
mất lịch sử.  Antigravity không phải thành viên của phiên này.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "thaoluan"
OUT = ROOT / "thaoluan.html"
MANIFEST = SRC / "manifest.json"
STATE = SRC / "state.json"

ORDER = ("codex", "claude")
PEOPLE = {
    "codex": ("#5aa9ff", "Codex"),
    "claude": ("#d9a066", "Claude"),
}
TURN_RE = re.compile(r"^(\d{3})-(codex|claude)\.html$")


def _configure_console() -> None:
    """Windows thường dùng cp1252; ép UTF-8 để thông báo tiếng Việt không làm hỏng build."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")

CSS = """
:root{color-scheme:dark;--bg:#17191d;--panel:#22252b;--line:#393d46;--muted:#9ba3af}
*{box-sizing:border-box} body{font-family:'Segoe UI',Tahoma,sans-serif;line-height:1.65;
margin:0 auto;padding:24px;max-width:980px;background:var(--bg);color:#e1e5ea}
h1{margin:0 0 8px;color:#fff}.subtitle{color:var(--muted);margin:0 0 22px}
.status,.rules{background:var(--panel);padding:16px 18px;border:1px solid var(--line);
border-radius:10px;margin-bottom:20px}.status strong{color:#8ee6aa}.grid{display:grid;
grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px}.pill{background:#191b20;
border:1px solid var(--line);padding:10px 12px;border-radius:8px}.label{display:block;
font-size:.78rem;color:var(--muted);text-transform:uppercase}.message{border:1px solid var(--line);
padding:18px 20px;margin:0 0 20px;border-radius:10px;background:var(--panel)}
.author{font-weight:750;margin-bottom:12px;font-size:1.08rem;display:flex;
justify-content:space-between;gap:12px}.hash{font:11px Consolas,monospace;color:var(--muted)}
code{background:#111318;padding:2px 6px;border-radius:4px;color:#efb58f}a{color:#7fc2ff}
@media(max-width:600px){body{padding:14px}.author{display:block}.hash{display:block;margin-top:4px}}
"""


class DiscussionBuildError(RuntimeError):
    """Dữ liệu lượt không hợp lệ hoặc lịch sử đã bị can thiệp."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_manifest() -> dict[str, str]:
    if not MANIFEST.exists():
        return {}
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if payload.get("order") != list(ORDER):
        raise DiscussionBuildError("Manifest không thuộc phiên Codex-Claude hiện tại")
    files = payload.get("files")
    if not isinstance(files, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in files.items()
    ):
        raise DiscussionBuildError("Manifest hỏng: trường files không hợp lệ")
    return files


def _discover_turns() -> list[tuple[int, str, Path]]:
    turns: list[tuple[int, str, Path]] = []
    for path in SRC.glob("*.html"):
        match = TURN_RE.fullmatch(path.name)
        if not match:
            raise DiscussionBuildError(
                f"Tên lượt sai: {path.name}; cần NNN-codex.html hoặc NNN-claude.html"
            )
        turns.append((int(match.group(1)), match.group(2), path))
    turns.sort(key=lambda row: row[0])
    for expected, (number, _speaker, _path) in enumerate(turns, start=1):
        if number != expected:
            raise DiscussionBuildError(
                f"Thiếu hoặc trùng lượt: chờ {expected:03d}, thấy {number:03d}"
            )
    # Xen lượt Codex→Claude là NHỊP MẶC ĐỊNH, không phải luật cứng: 08/08/2026
    # Codex hết hạn mức chạy công cụ tới 15/08, nên một bên phải làm nốt phần
    # của bên kia.  Hai bảo đảm thật sự quan trọng — đánh số liên tục và lời cũ
    # bất biến — vẫn giữ nguyên.  Người viết mỗi lượt hiện trên thẻ, nên việc
    # một bên viết hai lượt liền là chuyện AI ĐỌC ĐƯỢC, không phải chuyện giấu.
    return turns


def _validate_history(
    turns: list[tuple[int, str, Path]], old_manifest: dict[str, str]
) -> dict[str, str]:
    current = {path.name: _sha256(path) for _number, _speaker, path in turns}
    missing = sorted(set(old_manifest) - set(current))
    if missing:
        raise DiscussionBuildError(f"Lời cũ đã bị xóa: {', '.join(missing)}")
    changed = sorted(
        name for name, digest in old_manifest.items() if current.get(name) != digest
    )
    if changed:
        raise DiscussionBuildError(f"Lời cũ đã bị sửa: {', '.join(changed)}")
    old_numbers = [int(name[:3]) for name in old_manifest]
    last_old = max(old_numbers, default=0)
    inserted = sorted(int(name[:3]) for name in set(current) - set(old_manifest))
    if inserted and inserted[0] != last_old + 1:
        raise DiscussionBuildError("Chỉ được nối lượt mới vào cuối lịch sử")
    return current


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def build() -> int:
    SRC.mkdir(parents=True, exist_ok=True)
    try:
        turns = _discover_turns()
        old_manifest = _load_manifest()
        hashes = _validate_history(turns, old_manifest)
    except (DiscussionBuildError, json.JSONDecodeError) as exc:
        print(f"KHÔNG DỰNG: {exc}", file=sys.stderr)
        return 2

    completed = len(turns)
    next_speaker = ORDER[completed % len(ORDER)]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    state = {
        "schema_version": 1,
        "session_id": "aura-senior-coder-codex-claude-20260808",
        "order": list(ORDER),
        "completed_turns": completed,
        "next_turn": completed + 1,
        "next_speaker": next_speaker,
        "status": "WAITING_FOR_SPEAKER",
        "updated_at": now,
    }

    cards: list[str] = []
    for number, speaker, path in turns:
        color, display = PEOPLE[speaker]
        body = path.read_text(encoding="utf-8").strip()
        digest = hashes[path.name]
        cards.append(
            f'<article class="message" style="border-left:5px solid {color}">'
            f'<div class="author" style="color:{color}"><span>{html.escape(display)} · '
            f'Lượt {number}</span><span class="hash" title="SHA-256">{digest[:12]}</span></div>'
            f'<div class="content">{body}</div></article>'
        )

    document = f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="10">
<title>Codex ↔ Claude · Nâng cấp AURA</title><style>{CSS}</style></head><body>
<h1>Codex ↔ Claude: Nâng cấp năng lực CODE cho AURA</h1>
<p class="subtitle">Phiên mới bắt đầu từ đầu ngày 08/08/2026 · Tự làm mới mỗi 10 giây</p>
<section class="status"><strong>● Phòng đang chạy tự động</strong><div class="grid">
<div class="pill"><span class="label">Đã xong</span>{completed} lượt</div>
<div class="pill"><span class="label">Lượt kế</span>{completed + 1}</div>
<div class="pill"><span class="label">Người kế</span>{html.escape(PEOPLE[next_speaker][1])}</div>
<div class="pill"><span class="label">Thứ tự</span>Codex → Claude → lặp</div>
</div></section>
<section class="rules"><strong>Luật cứng</strong><ul>
<li>Chỉ Codex và Claude; không có thành viên thứ ba.</li>
<li>Mỗi lượt là một tệp bất biến. Sửa hoặc xóa lời cũ sẽ bị khóa dựng.</li>
<li>Hai bên tự chuyển lượt; Chủ không cần gõ “tiếp tục”.</li>
<li>Cuộc họp kết thúc khi có kế hoạch chung, thước đo, phân công và ETA — không nói vô hạn.</li>
</ul></section>
{chr(10).join(cards) if cards else '<p>Đang chờ Codex mở cuộc họp…</p>'}
</body></html>"""

    manifest_payload = {
        "schema_version": 1,
        "session_id": state["session_id"],
        "order": list(ORDER),
        "files": hashes,
        "updated_at": now,
    }
    _atomic_write(MANIFEST, json.dumps(manifest_payload, ensure_ascii=False, indent=2) + "\n")
    _atomic_write(STATE, json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    _atomic_write(OUT, document)
    print(
        f"Đã dựng {OUT.name}: {completed} lượt; kế tiếp {next_speaker} "
        f"(lượt {completed + 1:03d})"
    )
    return 0


if __name__ == "__main__":
    _configure_console()
    raise SystemExit(build())
