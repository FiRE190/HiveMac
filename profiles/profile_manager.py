"""
CRUD for local JSON profiles.  Tracks the last-used profile in
config/last_profile.txt so it auto-loads on startup.
"""
import json
import threading
from pathlib import Path
from typing import Optional

from utils.logger import get_logger

log = get_logger(__name__)

_PROFILES_DIR = Path(__file__).parent
_LAST_PROFILE_FILE = Path(__file__).parent.parent / "config" / "last_profile.txt"
_DEFAULT_PROFILE_PATH = _PROFILES_DIR / "default_profile.json"


def _load_default_template() -> dict:
    with open(_DEFAULT_PROFILE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


class ProfileManager:
    _instance: "ProfileManager | None" = None
    _cls_lock = threading.Lock()

    def __new__(cls) -> "ProfileManager":
        with cls._cls_lock:
            if cls._instance is None:
                inst = super().__new__(cls)
                inst._lock = threading.RLock()
                cls._instance = inst
        return cls._instance

    # ------------------------------------------------------------------ #

    def list_profiles(self) -> list[str]:
        with self._lock:
            return sorted(
                p.stem
                for p in _PROFILES_DIR.glob("*.json")
                if p.stem != "default_profile" and not p.stem.startswith("__")
            )

    def load(self, name: str) -> Optional[dict]:
        path = _PROFILES_DIR / f"{name}.json"
        if not path.exists():
            log.warning("Profile '%s' not found", name)
            return None
        with self._lock:
            with open(path, "r", encoding="utf-8") as f:
                profile = json.load(f)
            self._save_last_used(name)
            log.info("Loaded profile '%s'", name)
            return profile

    def save(self, profile: dict) -> None:
        name = profile.get("name", "unnamed")
        path = _PROFILES_DIR / f"{name}.json"
        with self._lock:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(profile, f, indent=2)
            self._save_last_used(name)
        log.info("Saved profile '%s'", name)

    def create(self, name: str) -> dict:
        profile = _load_default_template()
        profile["name"] = name
        self.save(profile)
        return profile

    def delete(self, name: str) -> bool:
        if name == "default":
            log.warning("Cannot delete the default profile")
            return False
        path = _PROFILES_DIR / f"{name}.json"
        if path.exists():
            path.unlink()
            log.info("Deleted profile '%s'", name)
            return True
        return False

    def load_last_used(self) -> dict:
        name = self._read_last_used()
        if name:
            profile = self.load(name)
            if profile:
                return profile
        # Fall back to default
        profile = self.load("default")
        if profile is None:
            profile = _load_default_template()
            self.save(profile)
        return profile

    def _save_last_used(self, name: str) -> None:
        _LAST_PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _LAST_PROFILE_FILE.write_text(name, encoding="utf-8")

    def _read_last_used(self) -> Optional[str]:
        if _LAST_PROFILE_FILE.exists():
            name = _LAST_PROFILE_FILE.read_text(encoding="utf-8").strip()
            return name if name else None
        return None


def get_profile_manager() -> ProfileManager:
    return ProfileManager()
