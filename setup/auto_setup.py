"""
Idempotent first run scaffolding: folders, a default profile, nothing else.
Config defaults live in config/default_config.json and are merged at load time.
"""
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
DIRS = ["config", "config/paths/user/to_field", "config/paths/user/to_hive", "profiles", "logs", "templates", "debug"]


def run_full_setup(verbose: bool = False) -> None:
    for d in DIRS:
        (ROOT / d).mkdir(parents=True, exist_ok=True)
    default_profile = ROOT / "profiles" / "default.json"
    template = ROOT / "profiles" / "default_profile.json"
    if not default_profile.exists() and template.exists():
        default_profile.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
        if verbose:
            print("[+] created profiles/default.json")
    gitignore = ROOT / ".gitignore"
    if gitignore.exists():
        text = gitignore.read_text(encoding="utf-8")
        wanted = ["config/paths/user/", "templates/*.png"]
        missing = [w for w in wanted if w not in text]
        if missing:
            gitignore.write_text(text.rstrip("\n") + "\n" + "\n".join(missing) + "\n", encoding="utf-8")
    try:
        json.loads(default_profile.read_text(encoding="utf-8"))
    except Exception:
        default_profile.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
