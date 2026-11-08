"""Build on a local Linux Docker host only after aggregate capacity checks."""
import argparse
import json
import os
import platform
import re
import stat
import subprocess
from pathlib import Path

from build_capacity import preflight


def build(context, config, tag, *, run=subprocess.run):
    if platform.system() != 'Linux':
        raise ValueError('Run on the Linux Docker host, not a remote client or Docker Desktop')
    if not re.fullmatch(r'[a-z0-9][a-z0-9._/-]*:[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}', tag):
        raise ValueError('An explicit image tag is required')
    context = context.resolve(strict=True)
    binding = json.loads((context / 'container-input.json').read_text())
    base = binding['base_image']
    if binding.get('platform') != 'linux/amd64' or not re.fullmatch(r'[a-z0-9][a-z0-9./:_-]*@sha256:[a-f0-9]{64}', base):
        raise ValueError('Invalid pinned build input')
    socket = Path('/var/run/docker.sock')
    if not stat.S_ISSOCK(socket.stat().st_mode):
        raise ValueError('Local Docker socket required')
    docker = ['docker', '--host', 'unix:///var/run/docker.sock']
    # Exclude environment-selected remote daemons/builders. docker driver keeps
    # the build in this daemon rather than an unrelated buildx builder.
    env = {k: v for k, v in os.environ.items() if not k.startswith(('DOCKER_', 'BUILDX_', 'BUILDKIT_'))}
    info = json.loads(run(docker + ['info', '--format', '{{json .}}'], check=True,
                          capture_output=True, text=True, timeout=30, env=env).stdout)
    root = Path(info['DockerRootDir']).resolve(strict=True)
    entries = config['storage']
    paths = {Path(e['path']).resolve(strict=True) for e in entries}
    if root not in paths or not any(context.is_relative_to(p) for p in paths):
        raise ValueError('Capacity must cover DockerRootDir and the build context')
    if 'containerd.snapshotter' in json.dumps(info.get('DriverStatus', [])):
        # Do not pretend DockerRootDir covers the separate image store.
        raise ValueError('Separate containerd image store requires a verified capacity adapter; build refused')
    report = preflight(entries)
    if report['result'] != 'PASS':
        raise ValueError('Insufficient aggregate build capacity')
    # Inspect the selected default builder; never create or bootstrap one here.
    builder = run(docker + ['buildx', 'inspect', 'default'], check=True,
                  capture_output=True, text=True, timeout=30, env=env).stdout
    if not re.search(r'^Driver:\s+docker\s*$', builder, re.MULTILINE):
        raise ValueError('Only the local docker build driver is supported')
    run(docker + ['buildx', 'build', '--builder', 'default', '--load', '--platform', 'linux/amd64',
                 '--build-arg', 'BASE_IMAGE=' + base, '--tag', tag, str(context)],
        check=True, timeout=3600, env=env)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context', type=Path, required=True)
    parser.add_argument('--capacity-config', type=Path, required=True)
    parser.add_argument('--tag', required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.context, json.loads(args.capacity_config.read_text()), args.tag)))


if __name__ == '__main__':
    main()
