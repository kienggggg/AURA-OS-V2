import pytest
from module import attempt


def test_exactly_the_requested_number_of_calls():
    calls = []

    def always_fails():
        calls.append(1)
        raise ValueError("hong")

    with pytest.raises(ValueError):
        attempt(always_fails, attempts=2)
    assert len(calls) == 2, f"goi {len(calls)} lan thay vi 2"
