from module import run_steps, Budget


def test_steps_stop_when_budget_is_gone():
    steps = [lambda i=i: (1.0, i) for i in range(10)]
    b = Budget(total_s=3.0)
    got = run_steps(steps, b)
    assert len(got) <= 3, f"chay {len(got)} buoc voi ngan sach 3 giay"
