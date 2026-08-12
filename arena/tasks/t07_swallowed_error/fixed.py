class BadRecord(ValueError):
    pass


def parse_record(line: str) -> dict:
    name, sep, score = line.partition("=")
    if not sep or not score.strip():
        raise BadRecord(f"dong khong hop le: {line!r}")
    try:
        value = int(score.strip())
    except ValueError as exc:
        raise BadRecord(f"diem khong phai so: {line!r}") from exc
    return {"name": name.strip(), "score": value}


def load_records(lines: list[str]) -> list[dict]:
    return [parse_record(line) for line in lines]


def total_score(lines: list[str]) -> int:
    return sum(r["score"] for r in load_records(lines))
