"""Phép đo về CÔNG CỤ ĐÃ CÀI TRÊN MÁY — của Codex, gộp về `tools/probes/`.

Nguyên bản `tools/local_tech_probes.py` (Codex). Chuyển về đây ngày 11/08/2026
để cả ba tệp phép đo nằm một chỗ và dùng chung `chung.py`. Giữ NGUYÊN từng
phép đo và từng tiêu chí đạt/không đạt; chỉ đổi hai thứ:

  - `_emit` -> `chung.emit` (cùng một hàm, cùng một kiểu in);
  - argparse -> `chung.chay` (kiểu tra `argv[1]`, chính là kiểu Codex đã dùng
    khi viết `hermes_openclaw_contract.py` hôm nay).

Luật gốc giữ nguyên: không cài gì, không ra Internet, in số đo chứ không in
nội dung tài liệu riêng của Sếp.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from chung import chay, emit as _emit  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ffmpeg() -> str | None:
    bundled = Path.home() / ".local" / "bin" / "ffmpeg.exe"
    if bundled.is_file():
        return str(bundled)
    return shutil.which("ffmpeg")


def ffmpeg_installed() -> int:
    executable = _ffmpeg()
    if not executable:
        _emit({"installed": False})
        return 1
    result = subprocess.run(
        [executable, "-version"], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=10,
    )
    first_line = (result.stdout or "").splitlines()[:1]
    _emit({"installed": result.returncode == 0, "version": first_line})
    return result.returncode


def ffmpeg_smoke() -> int:
    executable = _ffmpeg()
    if not executable:
        _emit({"ok": False, "reason": "ffmpeg not found"})
        return 1
    started = time.perf_counter()
    result = subprocess.run(
        [
            executable, "-hide_banner", "-loglevel", "error", "-f", "lavfi",
            "-i", "sine=frequency=1000:duration=0.2", "-f", "null", "-",
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=15,
    )
    _emit({
        "ok": result.returncode == 0,
        "operation": "generate 0.2 second sine wave and decode to null sink",
        "duration_ms": round((time.perf_counter() - started) * 1000),
    })
    return result.returncode


def _ollama() -> str | None:
    return shutil.which("ollama")


QWEN_MODELS = ("qwen3:0.6b", "qwen3:1.7b", "qwen3.5:4b")


def qwen_installed() -> int:
    executable = _ollama()
    if not executable:
        _emit({"installed": False, "models": {name: False for name in QWEN_MODELS}})
        return 1
    result = subprocess.run(
        [executable, "list"], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=15,
    )
    output = result.stdout or ""
    found = {name: name in output for name in QWEN_MODELS}
    _emit({"installed": result.returncode == 0 and all(found.values()), "models": found})
    return 0 if result.returncode == 0 and all(found.values()) else 1


def qwen_smoke() -> int:
    results: list[dict] = []
    all_reachable = True
    for model in QWEN_MODELS:
        body = json.dumps({
            "model": model,
            "prompt": "Chi tra loi dung mot tu: OK",
            "stream": False,
            "think": False,
            "keep_alive": 0,
            "options": {"temperature": 0, "num_predict": 8},
        }).encode("utf-8")
        request = urllib.request.Request(
            "http://127.0.0.1:11434/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                payload = json.loads(response.read().decode("utf-8"))
            text = str(payload.get("response") or "").strip()
            results.append({
                "model": model,
                "reachable": True,
                "wall_ms": round((time.perf_counter() - started) * 1000),
                "eval_count": payload.get("eval_count"),
                "exact_ok": text == "OK",
                "response": text,
            })
        except Exception as exc:  # noqa: BLE001 - probe must report infrastructure failures
            all_reachable = False
            results.append({
                "model": model,
                "reachable": False,
                "wall_ms": round((time.perf_counter() - started) * 1000),
                "exact_ok": False,
                "error": f"{type(exc).__name__}: {exc}",
            })
    _emit({
        "ok": all_reachable,
        "criterion": "all three local models completed one generation request",
        "instruction_exact_passes": sum(item["exact_ok"] for item in results),
        "instruction_exact_total": len(results),
        "results": results,
    })
    return 0 if all_reachable else 1


def moonshine_smoke() -> int:
    from core.hearing import transcribe

    sample = ROOT / "video_dub" / "voice_samples2" / "a_pitch0_rate20.mp3"
    started = time.perf_counter()
    result = transcribe(sample, "vi", timeout=180)
    payload = {
        "ok": bool(result.get("ok")),
        "wall_ms": round((time.perf_counter() - started) * 1000),
        "audio_seconds": result.get("seconds"),
        "character_count": len(result.get("text") or ""),
        "line_count": len(result.get("lines") or []),
    }
    if not result.get("ok"):
        payload["error"] = result.get("error")
    _emit(payload)
    return 0 if result.get("ok") else 1


def _qwen_audio_root() -> Path:
    return ROOT / ".tech" / "qwen-audio-agent"


def qwen_audio_installed() -> int:
    base = _qwen_audio_root()
    manifest = base / "node_modules" / "qwen-audio-agent" / "package.json"
    cli = base / "node_modules" / ".bin" / "qwenaudio.cmd"
    if not manifest.is_file() or not cli.is_file():
        _emit({"installed": False, "manifest": manifest.is_file(), "cli": cli.is_file()})
        return 1
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    summary = {
        "installed": True,
        "name": payload.get("name"),
        "version": payload.get("version"),
        "license": payload.get("license"),
        "cli_present": True,
    }
    _emit(summary)
    return 0 if (
        summary["name"] == "qwen-audio-agent"
        and summary["version"] == "1.8.1"
        and summary["license"] == "Apache-2.0"
    ) else 1


def qwen_audio_smoke() -> int:
    cli = _qwen_audio_root() / "node_modules" / ".bin" / "qwenaudio.cmd"
    if not cli.is_file():
        _emit({"ok": False, "reason": "isolated CLI missing"})
        return 1

    help_started = time.perf_counter()
    help_result = subprocess.run(
        [str(cli), "--help"], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30,
    )
    help_ms = round((time.perf_counter() - help_started) * 1000)

    setup_started = time.perf_counter()
    setup_result = subprocess.run(
        [str(cli), "setup", "--backend", "codex", "--json"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=30,
    )
    setup_ms = round((time.perf_counter() - setup_started) * 1000)
    try:
        setup = json.loads(setup_result.stdout or "{}")
    except json.JSONDecodeError:
        setup = {}
    backends = setup.get("backends") if isinstance(setup, dict) else []
    backend = backends[0] if isinstance(backends, list) and backends else {}
    backend_status = backend.get("backend") if isinstance(backend, dict) else {}
    adapter_status = backend.get("adapter") if isinstance(backend, dict) else {}
    # Deliberately omit executable paths and raw stdout.  The artifact proves
    # readiness without copying machine-specific or potentially sensitive data.
    redacted_setup = {
        "selected": setup.get("selected") if isinstance(setup, dict) else None,
        "read_only": setup.get("readOnly") if isinstance(setup, dict) else None,
        "backend_ready": backend_status.get("ready") if isinstance(backend_status, dict) else None,
        "adapter_ready": adapter_status.get("ready") if isinstance(adapter_status, dict) else None,
        "integration": backend.get("integration") if isinstance(backend, dict) else None,
        "configuration": backend.get("configuration") if isinstance(backend, dict) else None,
        "authentication": backend.get("authentication") if isinstance(backend, dict) else None,
        "issue_count": len(backend.get("issues") or []) if isinstance(backend, dict) else None,
    }
    ok = (
        help_result.returncode == 0
        and "setup" in (help_result.stdout or "").lower()
        and setup_result.returncode == 0
        and redacted_setup["selected"] == "codex"
        and redacted_setup["read_only"] is True
        and redacted_setup["backend_ready"] is True
        and redacted_setup["adapter_ready"] is True
    )
    _emit({
        "ok": ok,
        "scope": "CLI help plus read-only Codex setup readiness; no microphone or voice E2E",
        "help": {"exit_code": help_result.returncode, "duration_ms": help_ms},
        "setup": {"exit_code": setup_result.returncode, "duration_ms": setup_ms, **redacted_setup},
    })
    return 0 if ok else 1


MISSING_TECH = {
    "crawl4ai": ("crawl4ai", "crawl4ai"),
    "qwen-audio-agent": ("qwen_audio_agent", "qwen-audio-agent"),
    "book-to-skill": ("book_to_skill", "book-to-skill"),
    "lightrag": ("lightrag", "lightrag"),
}


def missing_check(technology: str) -> int:
    module, command = MISSING_TECH[technology]
    module_found = importlib.util.find_spec(module) is not None
    command_found = shutil.which(command) is not None
    _emit({
        "technology": technology,
        "module": module,
        "module_found": module_found,
        "command": command,
        "command_found": command_found,
    })
    return 0 if module_found or command_found else 1


# Bốn phép đo "còn thiếu" vốn là một lệnh con nhận tham số. `chay` chỉ nhận
# một tên, nên trải thành bốn tên — đổi lại mỗi phép đo có một tên gọi duy
# nhất để khai vào sổ, không phải ghép chuỗi lúc khai.
LENH = {
    "ffmpeg-installed": ffmpeg_installed,
    "ffmpeg-smoke": ffmpeg_smoke,
    "qwen-installed": qwen_installed,
    "qwen-smoke": qwen_smoke,
    "moonshine-smoke": moonshine_smoke,
    "qwen-audio-installed": qwen_audio_installed,
    "qwen-audio-smoke": qwen_audio_smoke,
    **{f"missing-{ten}": (lambda t=ten: missing_check(t)) for ten in MISSING_TECH},
}


if __name__ == "__main__":
    raise SystemExit(chay(LENH))
