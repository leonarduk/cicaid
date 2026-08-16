"""Shared pytest fixtures/setup.

The lib/ modules import each other with bare names (e.g. llm_common.py does
`from deepseek_review import ...`), relying on whichever top-level script
imports them having first put lib/ on sys.path (see e.g. review_issue.py).
Tests that import lib modules directly need that same sys.path entry.
"""

import sys
from pathlib import Path

import cicaid_devtools

_LIB_DIR = Path(cicaid_devtools.__file__).parent / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
