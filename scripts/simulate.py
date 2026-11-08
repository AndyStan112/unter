#!/usr/bin/env python3
"""Run the concurrent HTTP simulator using the project's Python environment."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'services/python'))
from unter.simulator import main

if __name__ == '__main__':
    main()
