import os
from pathlib import Path
from unittest.mock import Mock

import pytest
import bootstrap_release as boot


@pytest.fixture
def stage(tmp_path, monkeypatch):
    p = tmp_path / "staging"
    p.mkdir(mode=0o700)
    # Root ownership is tested on OCI. Unit tests use an unprivileged temp tree.
    monkeypatch.setattr(boot, "trusted", Mock())
    return p


def test_agent_checks_each_ancestor_and_leaf_without_writes(stage):
    calls = []
    before = stage.stat()
    boot.check_staging(stage, os.getuid(), lambda p, f: calls.append((p, f)) or True)
    assert calls == [(p, "-x") for p in reversed(stage.parents)] + [(stage, "-x"), (stage, "-w")]
    boot.trusted.assert_called_once_with(stage.parent)
    assert stage.stat().st_mode == before.st_mode
    assert list(stage.iterdir()) == []


def test_inaccessible_ancestor_reports_exact_path(stage):
    with pytest.raises(ValueError, match="cannot traverse staging ancestor: " + str(stage.parent)):
        boot.check_staging(stage, os.getuid(), lambda p, f: p != stage.parent)


def test_unwritable_leaf_is_rejected(stage):
    with pytest.raises(ValueError, match="lacks staging access -w"):
        boot.check_staging(stage, os.getuid(), lambda p, f: f != "-w")


def test_wrong_owner_and_shared_write_rejected(stage):
    with pytest.raises(ValueError, match="must belong to ocarun"):
        boot.check_staging(stage, os.getuid()+1, lambda *_: True)
    stage.chmod(0o777)
    with pytest.raises(ValueError, match="without group/other write"):
        boot.check_staging(stage, os.getuid(), lambda *_: True)


def test_symlink_rejected_before_chown(stage, monkeypatch):
    link = stage.parent / "link"
    link.symlink_to(stage, target_is_directory=True)
    chown = Mock()
    monkeypatch.setattr(boot.shutil, "chown", chown)
    with pytest.raises(ValueError, match="Unsafe existing staging"):
        boot.prepare_staging(link, os.getuid())
    chown.assert_not_called()


def test_unsafe_ancestor_stops_before_mutation(stage, monkeypatch):
    monkeypatch.setattr(boot, "trusted", Mock(side_effect=ValueError("Untrusted deployment path")))
    chown = Mock()
    monkeypatch.setattr(boot.shutil, "chown", chown)
    with pytest.raises(ValueError, match="Untrusted"):
        boot.prepare_staging(stage, os.getuid())
    chown.assert_not_called()


def test_filesystem_root_never_changes_owner(monkeypatch):
    chown = Mock()
    monkeypatch.setattr(boot.shutil, "chown", chown)
    with pytest.raises(ValueError, match="Filesystem root"):
        boot.prepare_staging(Path("/"), os.getuid())
    chown.assert_not_called()
