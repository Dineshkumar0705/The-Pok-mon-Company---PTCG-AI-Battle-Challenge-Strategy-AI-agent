"""Repo-root conftest: put src/ and vendor/ on sys.path for every test run,
so `pytest` works from a plain checkout without the caller having to set
PYTHONPATH by hand.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_ROOT, "src"), os.path.join(_ROOT, "vendor")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
