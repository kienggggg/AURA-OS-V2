import pytest
from module import Rover, MotorDriver


def test_backward_moves_the_other_way():
    d = MotorDriver()
    Rover(d).move("backward", 2.0)
    assert d.position == -2.0


def test_duration_is_respected():
    d = MotorDriver()
    Rover(d).move("forward", 0.5)
    assert d.position == 0.5


def test_offline_driver_must_not_return_ack():
    d = MotorDriver()
    d.online = False
    with pytest.raises(RuntimeError):
        Rover(d).move("forward", 1.0)


def test_failed_move_is_not_logged_as_done():
    d = MotorDriver()
    d.online = False
    rover = Rover(d)
    with pytest.raises(RuntimeError):
        rover.move("forward", 1.0)
    assert rover.log == []


def test_sequence_accumulates():
    d = MotorDriver()
    r = Rover(d)
    r.move("forward", 2.0)
    r.move("backward", 0.5)
    assert d.position == 1.5
