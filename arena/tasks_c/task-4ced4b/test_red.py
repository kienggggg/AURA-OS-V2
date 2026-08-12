import pytest
from module import run_all, Cancelled


def test_cancel_is_not_swallowed():
    def boom():
        raise Cancelled()

    with pytest.raises(Cancelled):
        run_all([lambda: 1, boom, lambda: 2])
