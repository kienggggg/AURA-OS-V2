from module import Sender, Transport


def test_sent_means_the_other_side_received_it():
    t = Transport()
    assert Sender(t).send("xin chao") == "SENT"
    assert t.delivered == ["xin chao"], "bao SENT nhung phia nhan khong co gi"
