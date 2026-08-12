from __future__ import annotations

import pytest

from evolution.validator import ASTValidator


def _blocked_calls(code: str) -> list[str]:
    return [finding.message for finding in ASTValidator().validate(code).blocks]


def test_collection_remove_is_not_mistaken_for_file_deletion():
    assert _blocked_calls("xs = [1, 2]\nxs.remove(1)\n") == []


@pytest.mark.parametrize(
    "code",
    [
        "import os\nos.remove('x')\n",
        "import os as operating_system\noperating_system.remove('x')\n",
        "from os import remove as rm\nrm('x')\n",
        "from pathlib import Path\nPath('x').unlink()\n",
    ],
)
def test_real_file_deletion_calls_remain_blocked(code: str):
    assert _blocked_calls(code)


def test_unrelated_object_method_named_unlink_is_not_blocked_by_name_alone():
    assert _blocked_calls("queue.unlink('item')\n") == []
