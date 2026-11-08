"""Read managed-runner capacity without installing packages or building images."""
import json
import os
import shutil
import subprocess
from pathlib import Path


def probe():
    info = json.loads(subprocess.check_output(['podman', '--remote=false', 'info', '--format', 'json'], text=True, timeout=30))
    store = info['store']
    paths = {'workspace': str(Path.cwd()), 'temporary': '/tmp',
             'podman_graphroot': store['graphRoot'], 'podman_runroot': store['runRoot']}
    reports = {}
    for name, value in paths.items():
        path = Path(value).resolve(strict=True)
        usage = shutil.disk_usage(path)
        fs = os.statvfs(path)
        reports[name] = {'path': str(path), 'device': path.stat().st_dev,
                         'total_bytes': usage.total, 'available_bytes': usage.free,
                         'available_inodes': fs.f_favail}
    limits = {}
    for name in ('memory.max', 'memory.current', 'cpu.max'):
        path = Path('/sys/fs/cgroup') / name
        if path.exists():
            limits[name] = path.read_text().strip()
    return {'schema_version': 1, 'engine': 'podman', 'version': info.get('version', {}).get('Version'),
            'storage_driver': store.get('graphDriverName'), 'paths': reports,
            'visible_cpus': os.cpu_count(), 'cgroup_v2': limits,
            'note': 'Read-only inventory; capacity approval and image build not performed'}


if __name__ == '__main__':
    print(json.dumps(probe(), sort_keys=True))
