from module import Watchdog


def test_late_ping_revives_before_tick_declares_death():
    w = Watchdog(timeout=1.0)
    w.ping(0.0)
    w.ping(1.5)          # trễ, nhưng ĐÃ tới nơi trước khi ai kiểm tra
    assert w.tick(1.6) is True
    assert w.stopped is False
