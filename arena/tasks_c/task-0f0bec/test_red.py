from module import Invoice


def test_three_dimes_make_thirty_cents():
    inv = Invoice()
    for _ in range(3):
        inv.add(0.1)
    assert inv.total() == 0.3, f"tong ra {inv.total()!r}"
