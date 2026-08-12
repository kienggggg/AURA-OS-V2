from module import Editor


def test_redo_restores_undone_text():
    e = Editor()
    e.type("a")
    e.undo()
    e.redo()
    assert e.text == "a"
