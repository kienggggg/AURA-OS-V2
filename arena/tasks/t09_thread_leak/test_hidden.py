from module import Worker


def test_single_submit_completes():
    w = Worker()
    w.submit(1)
    w.wait()
    assert w.done == [1]


def test_all_values_recorded():
    w = Worker()
    for i in range(100):
        w.submit(i)
    w.wait()
    assert sorted(w.done) == list(range(100))


def test_repeated_batches_do_not_accumulate():
    w = Worker()
    for _ in range(5):
        for i in range(60):
            w.submit(i)
        w.wait()
    assert len(w._threads) < 50


def test_wait_is_idempotent():
    w = Worker()
    w.submit(1)
    w.wait()
    w.wait()
    assert w.done == [1]
