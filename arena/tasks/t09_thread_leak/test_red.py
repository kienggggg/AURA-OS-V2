from module import Worker


def test_finished_threads_are_not_retained():
    w = Worker()
    for i in range(300):
        w.submit(i)
    w.wait()
    assert len(w._threads) < 50, f"con giu {len(w._threads)} luong da xong"
