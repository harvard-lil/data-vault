import json
import os
from pathlib import Path
from datetime import timedelta
import requests_cache


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


def cached_requests_session(
        cache_name: str = "data/request_cache",
        expire_after: timedelta = timedelta(days=1),
        **kwargs,
        ):
    """Cache requests using requests_cache."""
    return requests_cache.CachedSession(cache_name, expire_after=expire_after, **kwargs)
