"""
tools/registry.py
=================
SkillRegistry — cổng đăng ký "tay chân" của AURA theo triết lý Tiết lộ Lũy tiến
(Progressive Disclosure).

Mỗi skill là một thư mục tự mô tả trong skills/<skill-name>/:
  - SKILL.md      : Level 1-3 (metadata + khi nào dùng + hướng dẫn).
  - scripts/*.py  : Level 4 (code thực thi, CHỈ nạp khi gọi qua importlib).

Registry chỉ đọc text SKILL.md lúc quét (không import code) nên System Prompt chỉ
nhận name + description; code nặng (easyocr/bs4...) nạp trễ khi thực sự chạy.
Giữ hợp đồng cũ: execute_tool/dispatch/has/list_tools/register — luôn trả ToolResult.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from core.config import PROJECT_ROOT
from core.schemas import Task, ToolResult

logger = logging.getLogger("aura.tools.registry")

ToolFn = Callable[..., ToolResult]

SKILLS_ROOT: Path = PROJECT_ROOT / "skills"


@dataclass(frozen=True)
class SkillSpec:
    """Metadata đọc từ frontmatter SKILL.md. KHÔNG chứa code thực thi."""

    name: str
    description: str
    skill_dir: Path
    skill_md: Path
    entrypoint: str
    function: str

    @property
    def script_path(self) -> Path:
        return (self.skill_dir / self.entrypoint).resolve()


def _parse_frontmatter(block: str) -> dict[str, str]:
    """Parse YAML frontmatter. Ưu tiên PyYAML, fallback parser tối giản."""
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(block) or {}
        if isinstance(data, dict):
            return {str(k): ("" if v is None else str(v)) for k, v in data.items()}
    except Exception:  # noqa: BLE001
        pass

    out: dict[str, str] = {}
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, val = line.partition(":")
        out[key.strip()] = val.strip().strip('"').strip("'")
    return out


def _read_skill_md(path: Path) -> tuple[dict[str, str], str]:
    """Tách (frontmatter dict, body markdown) từ một SKILL.md."""
    text = path.read_text(encoding="utf-8")
    if text.lstrip().startswith("---"):
        parts = text.lstrip().split("---", 2)
        if len(parts) >= 3:
            return _parse_frontmatter(parts[1]), parts[2].lstrip("\n")
    return {}, text


class SkillRegistry:
    """Quét skills/, giữ metadata, nạp code TRỄ khi thực thi."""

    def __init__(self, skills_root: Path | None = None, *, auto_discover: bool = True) -> None:
        self._root = Path(skills_root) if skills_root else SKILLS_ROOT
        self._skills: dict[str, SkillSpec] = {}
        self._fn_cache: dict[str, ToolFn] = {}
        if auto_discover:
            self.discover()

    def discover(self) -> None:
        """Quét lại kho skill (đọc SKILL.md, KHÔNG import code). An toàn gọi lại."""
        self._skills.clear()
        if not self._root.is_dir():
            logger.warning("Chưa có thư mục skills tại %s — registry rỗng.", self._root)
            return
        for child in sorted(self._root.iterdir()):
            skill_md = child / "SKILL.md"
            if not (child.is_dir() and skill_md.is_file()):
                continue
            try:
                meta, _body = _read_skill_md(skill_md)
                spec = SkillSpec(
                    name=meta["name"],
                    description=meta.get("description", "").strip(),
                    skill_dir=child,
                    skill_md=skill_md,
                    entrypoint=meta["entrypoint"],
                    function=meta["function"],
                )
            except KeyError as exc:
                logger.error("Bỏ qua skill ở %s — thiếu trường %s.", child, exc)
                continue
            self._skills[spec.name] = spec

    def has(self, name: str) -> bool:
        return name in self._skills

    def catalog(self) -> list[tuple[str, str]]:
        """Level 1: (name, description) cho System Prompt."""
        return [(s.name, s.description) for s in self._skills.values()]

    def system_prompt_block(self) -> str:
        if not self._skills:
            return "Hiện chưa có skill nào được nạp."
        lines = ["Các skill khả dụng (gọi đúng tên qua tool dispatch):"]
        for name, desc in self.catalog():
            lines.append(f"- {name}: {desc}")
        return "\n".join(lines)

    def get_instructions(self, name: str) -> str:
        """Level 3: toàn văn SKILL.md (body) — nạp khi LLM đã chọn skill."""
        spec = self._skills.get(name)
        if spec is None:
            return f"Không tìm thấy skill '{name}'."
        _meta, body = _read_skill_md(spec.skill_md)
        return body

    def list_tools(self) -> list[SkillSpec]:
        return list(self._skills.values())

    def _load_fn(self, name: str) -> ToolFn:
        """Level 4: import script qua importlib và cache. Điểm DUY NHẤT nạp code skill."""
        if name in self._fn_cache:
            return self._fn_cache[name]
        spec = self._skills[name]
        script_path = spec.script_path
        if not script_path.is_file():
            raise FileNotFoundError(f"Script không tồn tại: {script_path}")
        mod_name = "aura_skill_" + name.replace(".", "_").replace("-", "_")
        module_spec = importlib.util.spec_from_file_location(mod_name, script_path)
        if module_spec is None or module_spec.loader is None:
            raise ImportError(f"Không tạo được import spec cho {script_path}")
        module = importlib.util.module_from_spec(module_spec)
        sys.modules[mod_name] = module
        module_spec.loader.exec_module(module)
        fn = getattr(module, spec.function, None)
        if fn is None or not callable(fn):
            raise AttributeError(f"Script '{script_path}' không có hàm '{spec.function}'.")
        self._fn_cache[name] = fn
        return fn

    def register_fn(self, name: str, fn: ToolFn, description: str = "") -> None:
        """Đăng ký tool RUNTIME (vd evolution engine) không qua file."""
        self._skills[name] = SkillSpec(
            name=name, description=description, skill_dir=self._root,
            skill_md=self._root / "__runtime__", entrypoint="<runtime>", function=name,
        )
        self._fn_cache[name] = fn

    def register(self, name: str, fn: ToolFn, description: str = "") -> None:
        """Alias kiểu cũ (evolution/loader.py) của register_fn()."""
        self.register_fn(name, fn, description)

    def execute_tool(self, tool_name: str, parameters: dict | None = None) -> ToolResult:
        """Chạy skill theo tên; mọi lỗi gói vào ToolResult, không ném ra ngoài."""
        if tool_name not in self._skills:
            return ToolResult.failure(
                tool_name, f"Skill '{tool_name}' chưa được khám phá trong kho skills/."
            )
        start = time.monotonic()
        try:
            fn = self._load_fn(tool_name)
        except Exception as exc:  # noqa: BLE001
            elapsed = int((time.monotonic() - start) * 1000)
            return ToolResult.failure(
                tool_name, f"Không nạp được code skill '{tool_name}': {exc}", elapsed
            )
        params = parameters or {}
        try:
            result = fn(**params)
        except TypeError as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            return ToolResult.failure(
                tool_name, f"Tham số không khớp cho '{tool_name}': {exc}", elapsed
            )
        except Exception as exc:  # noqa: BLE001
            elapsed = int((time.monotonic() - start) * 1000)
            return ToolResult.failure(
                tool_name, f"Skill '{tool_name}' lỗi runtime: {exc}", elapsed
            )
        elapsed = int((time.monotonic() - start) * 1000)
        if isinstance(result, ToolResult):
            if result.elapsed_ms == 0:
                result.elapsed_ms = elapsed
            return result
        return ToolResult.success(tool_name, output=str(result), elapsed_ms=elapsed)

    def dispatch(self, task: Task) -> ToolResult:
        return self.execute_tool(task.tool_name, task.arguments)


ToolRegistry = SkillRegistry

_DEFAULT_REGISTRY: SkillRegistry | None = None


def set_default_registry(reg: SkillRegistry) -> None:
    global _DEFAULT_REGISTRY
    _DEFAULT_REGISTRY = reg


def get_default_registry() -> SkillRegistry:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = SkillRegistry()
    return _DEFAULT_REGISTRY


def call_skill(name: str, parameters: dict | None = None) -> ToolResult:
    """Cho một skill gọi skill khác qua đúng cơ chế lazy-load (chia sẻ registry mặc định)."""
    return get_default_registry().execute_tool(name, parameters)


def build_default_registry(skills_root: Path | None = None) -> SkillRegistry:
    """Quét skills/ và ghim làm registry mặc định toàn cục (cho call_skill)."""
    reg = SkillRegistry(skills_root=skills_root)
    set_default_registry(reg)
    return reg


__all__ = [
    "SkillRegistry", "SkillSpec", "ToolRegistry", "ToolFn",
    "build_default_registry", "call_skill", "get_default_registry",
    "set_default_registry", "SKILLS_ROOT",
]
