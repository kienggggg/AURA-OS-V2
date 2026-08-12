from module import sort_names


def test_accented_name_sits_next_to_its_base_letter():
    got = sort_names(["Bình", "An", "Ánh", "Cường"])
    assert got == ["An", "Ánh", "Bình", "Cường"], got
