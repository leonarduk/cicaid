"""Shared pytest fixtures/setup.

The lib/ modules import each other with bare names (e.g. llm_common.py does
`from deepseek_review import ...`), relying on whichever top-level script
imports them having first put lib/ on sys.path (see e.g. review_issue.py).
Tests that import lib modules directly need that same sys.path entry.
"""

import sys
from pathlib import Path

# cicaid_devtools is a PEP 420 namespace package (no __init__.py, so no
# __file__) split across this repo and cicaid-pro's; derive the path to
# *this* repo's own lib/ from this file's location instead of the package.
_LIB_DIR = Path(__file__).resolve().parent.parent / "src" / "cicaid_devtools" / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
