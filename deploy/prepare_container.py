"""Create an isolated container context from a verified Linux release."""
import argparse
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

from verify_release import validate_result


def prepare(result, output, base_image):
    if not re.fullmatch(r'[a-z0-9][a-z0-9./:_-]*@sha256:[a-f0-9]{64}', base_image):
        raise ValueError('Base image must be a digest-pinned registry reference')
    if output.exists():
        raise ValueError('Output already exists')
    metadata = validate_result(result)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix='.container-') as temporary:
        context = Path(temporary) / 'context'
        context.mkdir()
        wheels = context / 'wheels'; wheels.mkdir()
        with zipfile.ZipFile(result / 'release.zip') as archive:
            # validate_result has checked flat allowlisted names and all hashes.
            for name in archive.namelist():
                if name != 'manifest.json':
                    (wheels / name).write_bytes(archive.read(name))
        shutil.copyfile(Path(__file__).parent / 'container/Dockerfile', context / 'Dockerfile')
        (context / 'release.json').write_text(json.dumps(metadata, indent=2) + '\n')
        (context / '.dockerignore').write_text('*\n!Dockerfile\n!wheels/\n!wheels/**\n!release.json\n')
        binding = {'base_image': base_image, 'platform': 'linux/amd64',
                   'app_version': metadata['app_version'], 'build_id': metadata['build_id'],
                   'bundle_sha256': metadata['bundle_sha256'], 'launchpad_commit': metadata['launchpad_commit']}
        (context / 'container-input.json').write_text(json.dumps(binding, indent=2) + '\n')
        if output.exists():
            raise ValueError('Output created concurrently')
        context.rename(output)
    return binding


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--base-image', required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.result, args.output, args.base_image)))


if __name__ == '__main__':
    main()
