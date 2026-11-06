from functools import lru_cache

from utils.appdirs import resource_root


@lru_cache(maxsize=1)
def app_version() -> str:
    try:
        return (resource_root() / "VERSION").read_text(encoding="utf-8").strip() or "dev"
    except OSError:
        return "dev"
