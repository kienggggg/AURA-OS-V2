# -*- coding: utf-8 -*-
"""Offline, secret-free contract probes for Hermes Agent and OpenClaw.

These probes never load a model, read user configuration, or contact a server.
They only inspect the installed package/clone and execute ``openclaw --version``.

Của Codex. Ngày 11/08/2026 chuyển sang dùng chung `chung.py` với hai tệp phép
đo còn lại; phép đo bên trong KHÔNG đổi một dòng nào.

`hermes-contract` ở đây THAY THẾ hẳn `do_cong_nghe.py hermes-context` của
Claude: cùng đọc `MINIMUM_CONTEXT_LENGTH`, nhưng bản này đọc kỹ hơn và là bản
sửa được kết luận sai "OpenClaw đòi tối thiểu 16K" (thật ra runtime chặn ở
4K, cảnh báo ở 8K).
"""
from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from chung import chay, emit  # noqa: E402


HERMES = Path("D:/hermes-agent")
OPENCLAW = Path.home() / "AppData/Roaming/npm/node_modules/openclaw"
OPENCLAW_CMD = Path.home() / "AppData/Roaming/npm/openclaw.cmd"


def _need(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def hermes_install() -> None:
    pyproject = HERMES / "pyproject.toml"
    _need(pyproject.is_file(), "Hermes pyproject.toml is missing")
    _need((HERMES / ".git").exists(), "Hermes clone metadata is missing")
    meta = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]
    commit = subprocess.run(
        ["git", "-C", str(HERMES), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=True,
    ).stdout.strip()
    _need(re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "invalid git commit")
    emit({
        "name": meta.get("name"),
        "version": meta.get("version"),
        "requires_python": meta.get("requires-python"),
        "license": meta.get("license"),
        "commit": commit,
    })


def hermes_contract() -> None:
    metadata = (HERMES / "agent/model_metadata.py").read_text(encoding="utf-8")
    providers = (HERMES / "hermes_cli/providers.py").read_text(encoding="utf-8")
    provider_test = (
        HERMES / "tests/hermes_cli/test_ollama_cloud_provider.py"
    ).read_text(encoding="utf-8")
    match = re.search(r"MINIMUM_CONTEXT_LENGTH\s*=\s*([\d_]+)", metadata)
    _need(match is not None, "Hermes context constant is missing")
    minimum = int(match.group(1).replace("_", ""))
    _need(minimum == 64_000, "unexpected Hermes context minimum")
    _need('"ollama": "custom"' in providers, "local Ollama alias is missing")
    _need('np("ollama") == "custom"' in provider_test, "provider assertion is missing")
    emit({
        "minimum_context_length": minimum,
        "ollama_alias": "custom",
        "provider_assertion_present": True,
        "model_called": False,
    })


def openclaw_install() -> None:
    package = OPENCLAW / "package.json"
    license_file = OPENCLAW / "LICENSE"
    _need(package.is_file(), "OpenClaw package.json is missing")
    _need(license_file.is_file(), "OpenClaw LICENSE is missing")
    meta = json.loads(package.read_text(encoding="utf-8"))
    _need(meta.get("name") == "openclaw", "unexpected package name")
    _need(meta.get("license") == "MIT", "unexpected package license")
    emit({
        "name": meta.get("name"),
        "version": meta.get("version"),
        "license": meta.get("license"),
        "repository": (meta.get("repository") or {}).get("url"),
    })


def openclaw_contract() -> None:
    _need(OPENCLAW_CMD.is_file(), "OpenClaw command shim is missing")
    result = subprocess.run(
        [str(OPENCLAW_CMD), "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=True,
    )
    version = result.stdout.strip().splitlines()[-1].strip()
    meta = json.loads((OPENCLAW / "package.json").read_text(encoding="utf-8"))
    _need(meta["version"] in version, "CLI and package versions differ")
    local_models = (OPENCLAW / "docs/gateway/local-models.md").read_text(encoding="utf-8")
    ollama = (OPENCLAW / "docs/providers/ollama.md").read_text(encoding="utf-8")
    _need("hard-blocking below 10% with a **4k** floor" in local_models,
          "4k context guard documentation is missing")
    _need("warning below 20% with an **8k** floor" in local_models,
          "8k context warning documentation is missing")
    _need("Ollama" in ollama and "/api/tags" in ollama,
          "Ollama provider documentation is missing")
    emit({
        "cli_version": version,
        "hard_floor_tokens": 4096,
        "warning_floor_tokens": 8192,
        "ollama_provider_docs": True,
        "model_called": False,
    })


def _boc(ham):
    """Giữ nguyên phân biệt của Codex: 1 = ĐO ĐƯỢC mà KHÔNG ĐẠT, 2 = KHÔNG ĐO ĐƯỢC.

    `_need` ném RuntimeError khi hợp đồng bị vi phạm — đó là một KẾT QUẢ, phải
    ra mã 1. Lỗi khác (thiếu tệp, tiến trình chết) là phép đo không chạy được,
    để `chung.chay` bắt và trả 2.
    """
    def chay_mot() -> int:
        try:
            ham()
        except (OSError, RuntimeError, KeyError, subprocess.SubprocessError) as exc:
            emit({"ok": False, "do_duoc": True, "vi_pham": str(exc)})
            return 1
        return 0
    return chay_mot


LENH = {
    "hermes-install": _boc(hermes_install),
    "hermes-contract": _boc(hermes_contract),
    "openclaw-install": _boc(openclaw_install),
    "openclaw-contract": _boc(openclaw_contract),
}


if __name__ == "__main__":
    raise SystemExit(chay(LENH))
