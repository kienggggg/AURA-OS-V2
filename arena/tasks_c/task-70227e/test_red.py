from module import Disk, save


def test_short_write_must_not_report_success():
    disk = Disk(capacity=3)
    assert save(disk, "mot dong dai") is False, "ghi thieu ma van bao thanh cong"
