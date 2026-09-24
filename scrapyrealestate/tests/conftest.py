"""Test configuration for the property search package."""
from __future__ import annotations

import sys
from pathlib import Path

# The repository intentionally has no installation metadata. Make the package
# importable when pytest is launched from the repository root or its subfolder.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
