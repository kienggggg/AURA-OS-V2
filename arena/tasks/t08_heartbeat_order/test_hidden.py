from module import Watchdog


def test_regular_pings_stay_alive():
    w = Watchdog(timeout=1.0)
    for t in (0.0, 0.5, 1.0, 1.5):
        w.ping(t)
        assert w.tick(t) is True


def test_silence_stops_it():
    w = Watchdog(timeout=1.0)
    w.ping(0.0)
    assert w.tick(2.0) is False
    assert w.stopped is True


def test_exactly_at_timeout_is_still_alive():
    w = Watchdog(timeout=1.0)
    w.ping(0.0)
    assert w.tick(1.0) is True


def test_stopped_is_terminal():
    w = Watchdog(timeout=1.0)
    w.ping(0.0)
    w.tick(5.0)
    w.ping(5.1)
    assert w.tick(5.2) is False


def test_no_ping_yet_is_alive():
    assert Watchdog(timeout=1.0).tick(99.0) is True


def test_delayed_ping_is_still_a_heartbeat():
    w = Watchdog(timeout=2.0)
    w.ping(0.0)
    w.ping(5.0)          # trễ, nhưng nhịp tim ĐÃ tới
    assert w.stopped is False
    assert w.tick(5.5) is True


def test_recovery_after_gap_repeats():
    w = Watchdog(timeout=1.0)
    for t in (0.0, 3.0, 6.0, 9.0):
        w.ping(t)
        assert w.tick(t + 0.1) is True, f"chet oan tai t={t}"


def test_ping_updates_last_seen_even_when_late():
    w = Watchdog(timeout=1.0)
    w.ping(0.0)
    w.ping(10.0)
    assert w.last_seen == 10.0
