from module import Registry


def test_unregister_releases_bookkeeping():
    r = Registry()
    for i in range(500):
        r.register("tam", lambda v: None)
        r.unregister("tam")
    assert len(r.history) <= 100, f"so lich su phinh len {len(r.history)} dong"
