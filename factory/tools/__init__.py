"""
factory/tools/__init__.py
==========================
TOOL_REGISTRY — danh mục ToolSpec của xưởng. Dashboard (`GET /api/tools`) và
skill chat (`skills/factory`) đều đọc từ đây; KHÔNG có danh mục thứ hai.

Đăng ký tool mới: viết `factory/tools/<ten>.py` với biến module-level `SPEC`
(ToolSpec) rồi import + `_register(SPEC)` bên dưới.
"""

from __future__ import annotations

from factory.models import ToolSpec

TOOL_REGISTRY: dict[str, ToolSpec] = {}


def _register(spec: ToolSpec) -> None:
    TOOL_REGISTRY[spec.name] = spec


from factory.tools import coloringbook as _coloring  # noqa: E402 — sau _register
from factory.tools import comic_create as _comic_new  # noqa: E402
from factory.tools import comic_translate as _comic  # noqa: E402
from factory.tools import content_create as _content  # noqa: E402
from factory.tools import echo as _echo  # noqa: E402
from factory.tools import excel_auto as _excel  # noqa: E402
from factory.tools import explainer_video as _explainer  # noqa: E402
from factory.tools import freelance_apply as _freelance  # noqa: E402
from factory.tools import novel_translate as _novel  # noqa: E402
from factory.tools import story_comic as _storycomic  # noqa: E402
from factory.tools import story_factory as _story  # noqa: E402
from factory.tools import story_kit as _storykit  # noqa: E402
from factory.tools import story_video as _storyvid  # noqa: E402
from factory.tools import video_batch as _video  # noqa: E402
from factory.tools import video_shorts as _shorts  # noqa: E402
from factory.tools import youtube_upload as _youtube  # noqa: E402

_register(_video.SPEC)
_register(_novel.SPEC)
_register(_comic.SPEC)
_register(_comic_new.SPEC)
_register(_youtube.SPEC)
_register(_story.SPEC)      # AURA tự viết truyện (THÍ NGHIỆM)
_register(_storykit.SPEC)   # bộ đồ nghề đăng Wattpad (văn án + bìa + tags)
_register(_storyvid.SPEC)   # truyện -> video kể chuyện (THÍ NGHIỆM)
_register(_storycomic.SPEC)  # truyện -> truyện tranh webtoon (GIAI ĐOẠN 2)
_register(_coloring.SPEC)    # sách tô màu bán Payhip/Etsy (kiếm tiền thụ động)
_register(_freelance.SPEC)   # bộ hồ sơ ứng tuyển: chấm hợp + pitch + phỏng vấn
_register(_explainer.SPEC)   # video faceless tiếng Anh thị trường Mỹ (CPM cao)
_register(_shorts.SPEC)      # video ngắn dọc footage thật (MoneyPrinterTurbo)
_register(_excel.SPEC)      # đợt 2 — hiện mờ "sắp có"
_register(_content.SPEC)    # đợt 2 — hiện mờ "sắp có"
_register(_echo.SPEC)


def get_tool(name: str) -> ToolSpec | None:
    return TOOL_REGISTRY.get(name)


def list_tools() -> list[ToolSpec]:
    return list(TOOL_REGISTRY.values())


__all__ = ["TOOL_REGISTRY", "get_tool", "list_tools"]
