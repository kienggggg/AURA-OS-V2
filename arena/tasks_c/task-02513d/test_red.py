from module import latest_per_key


def test_out_of_order_keeps_newest():
    events = [{"key": "a", "ts": 5, "v": "moi"}, {"key": "a", "ts": 1, "v": "cu"}]
    assert latest_per_key(events)["a"]["v"] == "moi"
