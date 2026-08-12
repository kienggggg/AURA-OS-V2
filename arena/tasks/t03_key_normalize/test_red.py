from module import Store


def test_uppercase_key_round_trips():
    s = Store()
    s.save("  Job.Scout  ", 42)
    assert s.load("Job.Scout") == 42
