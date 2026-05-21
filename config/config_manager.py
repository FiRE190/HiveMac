"""
Thread-safe JSON config manager.  Backfills missing keys from default_config.json
on every load so new keys are never absent.
"""
import json
import threading
from pathlib import Path
from typing import Any

_DEFAULTS_PATH = Path(__file__).parent / "default_config.json"
_USER_CONFIG_PATH = Path(__file__).parent / "settings.json"


def _deep_merge(base: dict, override: dict) -> dict:
    """Return base with override applied; missing nested keys filled from base."""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


class ConfigManager:
    _instance: "ConfigManager | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "ConfigManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._data: dict = {}
                cls._instance._rw_lock = threading.RLock()
                cls._instance._loaded = False
        return cls._instance

    # ------------------------------------------------------------------ #

    def load(self) -> None:
        with self._rw_lock:
            with open(_DEFAULTS_PATH, "r", encoding="utf-8") as f:
                defaults = json.load(f)
            if _USER_CONFIG_PATH.exists():
                with open(_USER_CONFIG_PATH, "r", encoding="utf-8") as f:
                    user = json.load(f)
                self._data = _deep_merge(defaults, user)
            else:
                self._data = dict(defaults)
            self._loaded = True

    def save(self) -> None:
        with self._rw_lock:
            _USER_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(_USER_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)

    def get(self, key_path: str, default: Any = None) -> Any:
        """Dot-separated key path, e.g. 'screen.scale_factor'."""
        with self._rw_lock:
            parts = key_path.split(".")
            node = self._data
            for p in parts:
                if isinstance(node, dict) and p in node:
                    node = node[p]
                else:
                    return default
            return node

    def set(self, key_path: str, value: Any) -> None:
        with self._rw_lock:
            parts = key_path.split(".")
            node = self._data
            for p in parts[:-1]:
                node = node.setdefault(p, {})
            node[parts[-1]] = value

    def get_section(self, section: str) -> dict:
        with self._rw_lock:
            return dict(self._data.get(section, {}))

    def set_region(self, name: str, region: dict) -> None:
        with self._rw_lock:
            self._data.setdefault("screen", {}).setdefault("regions", {})[name] = region
        self.save()


def get_config() -> ConfigManager:
    return ConfigManager()
