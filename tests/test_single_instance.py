"""CANH GÁC: AURA không được chạy đôi.

05/08/2026 phát hiện 2 daemon + 2 mascot + 2 health_guard cùng sống, do có HAI
launcher độc lập (AURA_OS.bat trong Startup + start_aura.bat bấm tay) -> mọi lệnh
bị nhân đôi. Khoá phải chặn được bản thứ hai, và KHÔNG kẹt khoá ma khi bản đầu chết.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest

from core import single_instance as si

_CHILD = textwrap.dedent(r"""
    import sys, time
    sys.path.insert(0, r"{root}")
    from core.single_instance import acquire
    print("OK" if acquire("{name}") else "BLOCKED", flush=True)
    time.sleep({hold})
""")


def _spawn(root, name, hold):
    return subprocess.Popen(
        [sys.executable, "-c", _CHILD.format(root=root, name=name, hold=hold)],
        stdout=subprocess.PIPE, text=True,
    )


@pytest.fixture
def root():
    from pathlib import Path
    return Path(__file__).resolve().parent.parent


def test_second_instance_is_blocked(root):
    """Bản thứ hai PHẢI bị chặn khi bản đầu còn sống."""
    first = _spawn(root, "pytest_lock_a", 4)
    try:
        assert first.stdout.readline().strip() == "OK"
        second = _spawn(root, "pytest_lock_a", 0)
        out = second.stdout.readline().strip()
        second.wait(timeout=15)
        assert out == "BLOCKED", "bản thứ hai lọt qua -> AURA sẽ chạy đôi"
    finally:
        first.kill(); first.wait(timeout=10)


def test_lock_released_when_process_dies(root):
    """Bản đầu chết -> khoá phải nhả (không kẹt 'khoá ma' sau khi tắt máy đột ngột)."""
    first = _spawn(root, "pytest_lock_b", 30)
    assert first.stdout.readline().strip() == "OK"
    first.kill(); first.wait(timeout=10)

    again = _spawn(root, "pytest_lock_b", 0)
    out = again.stdout.readline().strip()
    again.wait(timeout=15)
    assert out == "OK", "khoá còn kẹt sau khi tiến trình chết -> AURA không khởi động lại được"


def test_different_parts_do_not_block_each_other(root):
    """daemon / mascot / health_guard là 3 khoá RIÊNG, không chặn nhau."""
    procs = [_spawn(root, n, 3) for n in ("pytest_p1", "pytest_p2", "pytest_p3")]
    try:
        assert [p.stdout.readline().strip() for p in procs] == ["OK", "OK", "OK"]
    finally:
        for p in procs:
            p.kill(); p.wait(timeout=10)


def test_lock_failure_does_not_block_startup(monkeypatch):
    """Khoá hỏng thì AURA VẪN phải khởi động được (không được tự chặn mình)."""
    def boom(_name):
        raise OSError("mutex hỏng")
    monkeypatch.setattr(si, "_acquire_windows", boom)
    monkeypatch.setattr(si, "_acquire_posix", boom)
    assert si.acquire("bat_ky") is True
