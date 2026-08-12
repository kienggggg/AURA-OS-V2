def parse_record(line: str) -> dict:
    name, _, score = line.partition("=")
    return {"name": name.strip(), "score": int(score)}


def load_records(lines: list[str]) -> list[dict]:
    out = []
    for line in lines:
        try:
            out.append(parse_record(line))
        except Exception:
            pass
    return out


def total_score(lines: list[str]) -> int:
    return sum(r["score"] for r in load_records(lines))
