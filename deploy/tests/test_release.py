import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "activate", Path(__file__).parents[1] / "activate_release.py"
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


@pytest.fixture
def config():
    return json.loads((Path(__file__).parents[1] / "release.example.json").read_text())


def test_success(config, tmp_path):
    dropin = tmp_path / "release.conf"
    result = m.activate(
        config,
        "memory-0.4.0",
        dropin,
        lambda _: None,
        lambda _: {"status": "UP", "version": "0.3.0"},
        lambda *_: True,
    )
    assert result["previous_version"] == "0.3.0"
    assert "/memory-0.4.0/venv/bin/python" in dropin.read_text()


@pytest.mark.parametrize("existing", [None, b"[Service]\n# previous\n"])
def test_unhealthy_release_restores_exact_previous(config, tmp_path, existing):
    dropin = tmp_path / "release.conf"
    if existing is not None:
        dropin.write_bytes(existing)
    checks = []

    def wait(port, version, timeout):
        checks.append(version)
        return version == "0.3.0"

    with pytest.raises(RuntimeError, match="previous version restored"):
        m.activate(
            config,
            "memory-0.4.0",
            dropin,
            lambda _: None,
            lambda _: {"status": "UP", "version": "0.3.0"},
            wait,
        )
    assert checks == ["0.4.0", "0.3.0"]
    assert (dropin.read_bytes() if dropin.exists() else None) == existing


def test_restart_failure_recovers(config, tmp_path):
    calls = []

    def restart(service):
        calls.append(service)
        if len(calls) == 1:
            raise OSError("restart failed")

    with pytest.raises(RuntimeError, match="previous version restored"):
        m.activate(
            config,
            "memory-0.4.0",
            tmp_path / "release.conf",
            restart,
            lambda _: {"status": "UP", "version": "0.3.0"},
            lambda *_: True,
        )
    assert len(calls) == 2


def test_failed_recovery_is_not_success(config, tmp_path):
    with pytest.raises(RuntimeError, match="recovery also failed"):
        m.activate(
            config,
            "memory-0.4.0",
            tmp_path / "release.conf",
            lambda _: None,
            lambda _: {"status": "UP", "version": "0.3.0"},
            lambda *_: False,
        )


@pytest.mark.parametrize("alias", ["../etc", "x;id", "unknown"])
def test_rejects_unregistered_or_unsafe_release(config, alias):
    with pytest.raises((ValueError, KeyError)):
        m.validate(config, alias)


def test_unhealthy_baseline_does_not_change_service(config, tmp_path):
    dropin = tmp_path / "release.conf"
    with pytest.raises(RuntimeError, match="Current release"):
        m.activate(
            config,
            "memory-0.4.0",
            dropin,
            lambda _: None,
            lambda _: {"status": "DOWN"},
            lambda *_: True,
        )
    assert not dropin.exists()
