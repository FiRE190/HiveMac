"""
Where things live.

  resources   code and shipped defaults (default config, default profile, Natro paths).
              The repo folder in development, Contents/Resources/app inside HiveMac.app.
  data        what the user creates: settings, profiles, logs, templates, own recorded walks.
              The repo folder in development (same layout as before), and
              ~/Library/Application Support/HiveMac when running from the app bundle,
              because the bundle is replaced on every update and must stay read only.

HIVEMAC_HOME overrides the data folder (tests, a second profile set).
"""
from __future__ import annotations

import os
from pathlib import Path


def resource_root() -> Path:
    return Path(__file__).resolve().parent.parent


def is_bundled(root: Path | None = None) -> bool:
    return ".app/Contents/Resources" in str(root or resource_root())


def data_dir() -> Path:
    env = os.environ.get("HIVEMAC_HOME")
    if env:
        return Path(env).expanduser()
    if is_bundled():
        return Path.home() / "Library" / "Application Support" / "HiveMac"
    return resource_root()


def settings_path() -> Path:
    return data_dir() / "config" / "settings.json"


def last_profile_path() -> Path:
    return data_dir() / "config" / "last_profile.txt"


def profiles_dir() -> Path:
    return data_dir() / "profiles"


def logs_dir() -> Path:
    return data_dir() / "logs"


def debug_dir() -> Path:
    return data_dir() / "debug"


def templates_dir() -> Path:
    return data_dir() / "templates"


def user_paths_dir() -> Path:
    return data_dir() / "config" / "paths" / "user"


def ensure_dirs() -> None:
    for d in (settings_path().parent, profiles_dir(), logs_dir(), debug_dir(), templates_dir(),
              user_paths_dir() / "to_field", user_paths_dir() / "to_hive"):
        d.mkdir(parents=True, exist_ok=True)
