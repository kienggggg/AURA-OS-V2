import pytest
from module import Journal


def test_failed_write_is_not_marked_committed():
    def sink(entry):
        raise IOError("dia day")

    j = Journal(sink)
    with pytest.raises(IOError):
        j.write("a")
    assert j.committed == [], f"da danh dau xong du ghi that bai: {j.committed}"
