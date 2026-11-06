from pathlib import Path

from utils import appdirs


def test_bundle_detection():
    assert appdirs.is_bundled(Path("/Applications/HiveMac.app/Contents/Resources/app"))
    assert not appdirs.is_bundled(Path("/Users/me/Projects/HiveMac"))


def test_env_override_moves_all_user_data(monkeypatch, tmp_path):
    monkeypatch.setenv("HIVEMAC_HOME", str(tmp_path))
    assert appdirs.data_dir() == tmp_path
    appdirs.ensure_dirs()
    for d in (appdirs.profiles_dir(), appdirs.logs_dir(), appdirs.templates_dir(), appdirs.settings_path().parent,
              appdirs.user_paths_dir() / "to_field"):
        assert d.is_dir() and str(d).startswith(str(tmp_path)), d


def test_default_data_dir_is_the_repo_in_development(monkeypatch):
    monkeypatch.delenv("HIVEMAC_HOME", raising=False)
    assert appdirs.data_dir() == appdirs.resource_root()


def test_version_file_is_read():
    from utils.version import app_version
    assert app_version() not in ("", "dev")
