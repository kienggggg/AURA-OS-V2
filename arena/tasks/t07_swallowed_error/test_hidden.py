import pytest
from module import total_score, load_records, parse_record


def test_all_valid_sums():
    assert total_score(["a=1", "b=2"]) == 3


def test_parse_single():
    assert parse_record("x = 5") == {"name": "x", "score": 5}


def test_missing_separator_raises():
    with pytest.raises(Exception):
        parse_record("khong co dau bang")


def test_empty_score_raises():
    with pytest.raises(Exception):
        parse_record("a=")


def test_load_records_keeps_every_valid_row():
    assert len(load_records(["a=1", "b=2", "c=3"])) == 3


def test_error_message_names_the_bad_line():
    try:
        parse_record("b=xx")
    except Exception as exc:
        assert "b=xx" in str(exc)
    else:
        raise AssertionError("phai nem loi")
