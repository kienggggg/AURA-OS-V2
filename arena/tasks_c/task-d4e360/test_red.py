from module import MovingAverage


def test_old_samples_leave_the_average():
    m = MovingAverage(size=2)
    m.add(100.0)
    m.add(0.0)
    m.add(0.0)
    assert m.value() == 0.0, f"mau cu 100 van con trong trung binh: {m.value()}"
