"""Install and pair the dedicated Vivo AURA Avatar over authorized ADB."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from core.aura_avatar_pairing import pairing
from core.config import PROJECT_ROOT, settings

PACKAGE = "vn.aura.avatar"
ACTIVITY = f"{PACKAGE}/.MainActivity"
DEFAULT_APK = (
    PROJECT_ROOT / "android" / "aura-avatar" / "app" / "build"
    / "outputs" / "apk" / "debug" / "app-debug.apk"
)


def _run(adb_path: str, args: list[str], timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
    kwargs: dict = {"capture_output": True, "text": True, "timeout": timeout}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return subprocess.run([adb_path, *args], **kwargs)


def connected_devices(
    adb_path: str = "adb",
    runner: Callable[..., subprocess.CompletedProcess[str]] = _run,
) -> list[str]:
    try:
        result = runner(adb_path, ["devices"], timeout=15.0)
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    devices: list[str] = []
    for line in result.stdout.splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 2 and fields[1] == "device":
            devices.append(fields[0])
    return devices


def _select_device(
    adb_path: str,
    serial: str,
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> str:
    devices = connected_devices(adb_path, runner)
    selected = serial.strip()
    if selected:
        if selected not in devices:
            raise RuntimeError("Vivo chưa được ADB cấp quyền hoặc không đúng serial.")
        return selected
    if len(devices) == 1:
        return devices[0]
    if not devices:
        raise RuntimeError("Chưa thấy Vivo đã cấp quyền ADB.")
    raise RuntimeError("Có nhiều điện thoại ADB; cần chọn đúng Vivo để tránh cài nhầm.")


def _validated_endpoint(endpoint: str, default: str) -> str:
    selected = endpoint.strip() or default
    parsed = urlparse(selected)
    if parsed.scheme != "http" or not parsed.hostname or parsed.path != "/v1/avatar/chat":
        raise ValueError("Endpoint AURA Avatar phải là URL HTTP đúng đường /v1/avatar/chat.")
    return selected


def configure_phone(
    *,
    endpoint: str = "",
    adb_path: str = "adb",
    serial: str = "",
    runner: Callable[..., subprocess.CompletedProcess[str]] = _run,
) -> str:
    selected = _select_device(adb_path, serial, runner)
    config = pairing()
    target = _validated_endpoint(endpoint, config["endpoint"])
    result = runner(
        adb_path,
        [
            "-s", selected, "shell", "am", "start", "-n", ACTIVITY,
            "--es", "aura_endpoint", target,
            "--es", "aura_token", config["token"],
        ],
        timeout=25.0,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Không cấu hình được AURA Avatar: "
            + (result.stderr.strip() or result.stdout.strip())
        )
    return "Đã ghép Vivo với cầu AURA Avatar riêng."


def pair_and_install(
    *,
    apk: Path = DEFAULT_APK,
    adb_path: str = "adb",
    serial: str = "",
    endpoint: str = "",
    runner: Callable[..., subprocess.CompletedProcess[str]] = _run,
) -> str:
    if not apk.is_file():
        raise FileNotFoundError(f"Chưa thấy APK AURA Avatar: {apk}")
    selected = _select_device(adb_path, serial, runner)
    prefix = ["-s", selected]
    port = settings.aura_avatar_lan_port
    reverse = runner(
        adb_path, [*prefix, "reverse", f"tcp:{port}", f"tcp:{port}"], timeout=20.0
    )
    if reverse.returncode != 0:
        raise RuntimeError("Không tạo được cầu USB riêng cho AURA Avatar.")
    install = runner(adb_path, [*prefix, "install", "-r", str(apk)], timeout=90.0)
    if install.returncode != 0:
        raise RuntimeError(
            "Không cài được AURA Avatar: "
            + (install.stderr.strip() or install.stdout.strip())
        )
    configure_phone(
        endpoint=endpoint, adb_path=adb_path, serial=selected, runner=runner
    )
    return "Đã cài và ghép AURA Avatar trên Vivo qua USB."


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(description="Cài/cấu hình AURA Avatar cho Vivo")
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--configure", action="store_true")
    parser.add_argument("--apk", type=Path, default=DEFAULT_APK)
    parser.add_argument("--adb", default=getattr(settings, "adb_path", "adb"))
    parser.add_argument("--serial", default="")
    parser.add_argument("--endpoint", default="")
    args = parser.parse_args()
    if args.install:
        print(pair_and_install(
            apk=args.apk, adb_path=args.adb, serial=args.serial, endpoint=args.endpoint
        ))
    elif args.configure:
        print(configure_phone(
            endpoint=args.endpoint, adb_path=args.adb, serial=args.serial
        ))
    else:
        devices = connected_devices(args.adb)
        print("Android ADB sẵn sàng: " + ", ".join(devices) if devices else "Chưa có Android ADB.")


if __name__ == "__main__":
    main()
