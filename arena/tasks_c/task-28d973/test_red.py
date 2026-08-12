from module import Pool


def test_released_items_are_not_still_marked_in_use():
    pool = Pool(size=2)
    for _ in range(500):
        item = pool.acquire()
        pool.release(item)
    assert len(pool.in_use) <= 2, f"dang giu {len(pool.in_use)} muc 'dang dung'"
