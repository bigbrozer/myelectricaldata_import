"""Regression tests for bugs fixed in the src/ review (Phase 1)."""


def test_str2bool_and_is_bool():
    from dependencies import is_bool, str2bool

    assert str2bool("True") is True
    assert str2bool(1) is True
    assert str2bool(None) is False
    assert str2bool("no") is False
    assert is_bool("yes") and is_bool("False") and is_bool(0)
    assert not is_bool("maybe") and not is_bool(2.5)
