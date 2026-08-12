from module import send_batch


def test_one_failure_means_the_batch_failed():
    def sender(item):
        if item == "b":
            raise IOError("rot mang")

    status, failed = send_batch(["a", "b", "c"], sender)
    assert status == "FAILED", f"1/3 hong ma van bao {status}"
    assert failed == ["b"]
