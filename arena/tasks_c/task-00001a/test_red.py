import pytest
from module import topo_sort, CycleError


def test_cycle_is_detected():
    with pytest.raises(CycleError):
        topo_sort({"a": ["b"], "b": ["a"]})
