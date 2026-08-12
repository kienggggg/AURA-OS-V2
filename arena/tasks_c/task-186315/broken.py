def apply_edits(lines: list[str], edits: list[tuple[str, int, str]]) -> list[str]:
    """Áp các sửa đổi lên bản GỐC.  Mọi chỉ số đều tính theo `lines` ban đầu.

    Mỗi sửa đổi là (thao_tac, chi_so, noi_dung) với thao tác thuộc
    {"replace", "insert", "delete"}.  "insert" chèn TRƯỚC chỉ số đó.
    """
    out = list(lines)
    for op, index, text in edits:
        if op == "replace":
            out[index] = text
        elif op == "insert":
            out.insert(index, text)
        elif op == "delete":
            del out[index]
    return out
