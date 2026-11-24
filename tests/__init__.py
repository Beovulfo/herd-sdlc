"""The plugin lives in plugin/; put it on the import path so tests can `from scripts import herd`."""
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent.parent / "plugin"
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))
