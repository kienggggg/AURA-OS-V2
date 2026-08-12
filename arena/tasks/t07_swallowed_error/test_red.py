import pytest
from module import total_score


def test_bad_line_is_not_silently_dropped():
    lines = ["a=1", "b=xx", "c=3"]
    with pytest.raises(Exception):
        total_score(lines)
