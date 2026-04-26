from __future__ import annotations

import os
import time

import pytest

from jkcheese.single_instance import SingleInstance


@pytest.mark.skipif(os.name != "nt", reason="Windows mutex behavior only")
def test_single_instance_rejects_second_gui_instance():
    name = f"Local\\JkcheeseTest{os.getpid()}{int(time.time() * 1000)}"
    first = SingleInstance(name)
    second = SingleInstance(name)
    try:
        assert first.acquire() is True
        assert second.acquire() is False
    finally:
        second.release()
        first.release()
