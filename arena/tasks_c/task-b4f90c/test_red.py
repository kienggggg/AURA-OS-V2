from module import Store


def test_listener_sees_the_new_value_already_stored():
    store = Store()
    seen = []
    store.subscribe(lambda v: seen.append(store.value))
    store.set(42)
    assert seen == [42], f"nguoi nghe thay trang thai cu: {seen}"
