from module import Rover, MotorDriver


def test_ack_means_the_wheels_actually_turned():
    d = MotorDriver()
    rover = Rover(d)
    assert rover.move("forward", 3.0) == "ACK:FORWARD"
    assert d.position == 3.0, "bao ACK nhung banh khong quay"
