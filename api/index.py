"""Vercel Serverless Function Entrypoint for GRIDPOINT.
"""

import os
import sys

# Ensure repository root directory is on Python path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app import app

# Vercel's Python runtime automatically detects the ASGI 'app' instance
