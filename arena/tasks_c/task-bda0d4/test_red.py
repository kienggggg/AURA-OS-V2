from module import slot_for


def test_duplicate_goes_before_the_existing_one():
    assert slot_for([1, 2, 2, 3], 2) == 1
