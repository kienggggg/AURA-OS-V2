from module import RingLog


def test_bulk_add_respects_the_limit():
    log = RingLog(limit=3)
    log.add_many([f"d{i}" for i in range(100)])
    assert len(log.lines) == 3, f"giu {len(log.lines)} dong"
