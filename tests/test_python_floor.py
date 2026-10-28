"""macOS /usr/bin/python3 is 3.9. This plugin's tests use 3.10 union types."""
import sys

import pytest


def test_python_floor():
    if sys.version_info < (3, 10):
        pytest.skip(
            "Python 3.9 cannot read the X | Y type form. Hermes runs on 3.11 or newer."
        )
