import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path


def test_distribution_declares_console_script_and_current_mit_metadata() -> None:
    metadata = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert metadata["project"]["license"] == "MIT"
    assert metadata["project"]["scripts"]["qqnt-export"] == "qqnt_export.cli:main"


def test_git_tracks_no_database_or_key_artifacts() -> None:
    tracked = subprocess.check_output(["git", "ls-files", "-z"], text=True).split("\x00")
    forbidden = {".db", ".wal", ".shm", ".key", ".sqlite"}
    assert not [name for name in tracked if Path(name).suffix.casefold() in forbidden]


def test_built_wheel_includes_compatibility_metadata(tmp_path: Path) -> None:
    subprocess.run([sys.executable, "-m", "build", "--wheel", "--outdir", str(tmp_path)], check=True, capture_output=True)
    wheel = next(tmp_path.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
    assert "qqnt_export/resources/compatibility_matrix.json" in names
    assert "qqnt_export/adapters/clean_room_notes.md" in names
