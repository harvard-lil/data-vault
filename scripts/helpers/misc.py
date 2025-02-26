import json
import os
from pathlib import Path

CONFIG_PATH = (os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")) / "data-vault" / "config.json"

def load_config():
    """Load configuration from config file."""
    if CONFIG_PATH.exists():
        config = json.loads(CONFIG_PATH.read_text())
    else:
        config = {}
    return config 


def json_default(obj):
    """Default JSON encoder for serializing datetime objects."""
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    return super().default(obj)