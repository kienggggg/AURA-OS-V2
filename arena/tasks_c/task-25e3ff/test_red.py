from module import load_plugins


def test_failing_plugin_is_reported_broken():
    def bad():
        raise ImportError("thieu thu vien")

    loaded, broken = load_plugins([("tot", lambda: None), ("hong", bad)])
    assert broken == ["hong"], f"da nap={loaded} hong={broken}"
