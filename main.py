#!/usr/bin/env python3
"""AI Guardian - main entry point.

Run directly with:
    python main.py

Or install the package and use the `guardian` command.
"""

import sys
from pathlib import Path

# Allow running from a source checkout without installing.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from guardian.cli.app import main  # noqa: E402

if __name__ == "__main__":
    main()
