import json
import os
from pathlib import Path

CONFIG_PATH = (os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")) / "data-mirror" / "config.json"

def load_config():
    """Load configuration from config file."""
    if CONFIG_PATH.exists():
        config = json.loads(CONFIG_PATH.read_text())
    else:
        config = {}
    return config 