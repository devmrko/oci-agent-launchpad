import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parents[1]))
from probe_build_runner import probe


def test_probe_reports_real_filesystems_without_sensitive_engine_fields(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    info = {'store': {'graphRoot': str(tmp_path), 'runRoot': str(tmp_path), 'graphDriverName': 'overlay'},
            'version': {'Version': 'test'}, 'host': {'secret': 'must-not-export'}}
    calls = []
    def output(command, **kwargs):
        calls.append(command)
        return json.dumps(info)
    monkeypatch.setattr('probe_build_runner.subprocess.check_output', output)
    result = probe()
    assert result['paths']['workspace']['device'] == tmp_path.stat().st_dev
    assert result['paths']['workspace']['available_bytes'] > 0
    assert 'must-not-export' not in json.dumps(result)
    assert calls == [['podman', '--remote=false', 'info', '--format', 'json']]
