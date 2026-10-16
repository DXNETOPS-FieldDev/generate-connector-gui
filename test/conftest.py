"""pytest configuration — adds lib/ and test/ to sys.path."""

import os
import sys

_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR  = os.path.normpath(os.path.join(_TEST_DIR, "..", "lib"))

for _p in (_LIB_DIR, _TEST_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)
