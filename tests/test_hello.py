import pytest


def test_hoge():
    from sim.hello import hoge

    assert hoge() == 42
