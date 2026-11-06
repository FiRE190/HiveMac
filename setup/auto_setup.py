"""
Idempotent first run scaffolding: the data folders and a default profile.
Config defaults live in config/default_config.json and are merged at load time.
"""
import json
from pathlib import Path

from utils import appdirs

RESOURCES = appdirs.resource_root()


def run_full_setup(verbose: bool = False) -> None:
    appdirs.ensure_dirs()
    template = RESOURCES / "profiles" / "default_profile.json"
    default_profile = appdirs.profiles_dir() / "default.json"
    if not default_profile.exists() and template.exists():
        default_profile.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
        if verbose:
            print(f"[+] created {default_profile}")
    try:
        json.loads(default_profile.read_text(encoding="utf-8"))
    except Exception:
        default_profile.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
    if not appdirs.is_bundled():
        gitignore = Path(RESOURCES) / ".gitignore"
        if gitignore.exists():
            text = gitignore.read_text(encoding="utf-8")
            missing = [w for w in ("config/paths/user/", "templates/*.png") if w not in text]
            if missing:
                gitignore.write_text(text.rstrip("\n") + "\n" + "\n".join(missing) + "\n", encoding="utf-8")
