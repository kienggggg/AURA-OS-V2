import pytest
from module import Config


def test_failed_load_is_retried():
    state = {"n": 0}

    def loader():
        state["n"] += 1
        if state["n"] == 1:
            raise IOError("mang chua len")
        return {"ten": "AURA"}

    cfg = Config(loader)
    with pytest.raises(IOError):
        cfg.get("ten")
    assert cfg.get("ten") == "AURA", "lan dau hong la cau hinh rong vinh vien"
