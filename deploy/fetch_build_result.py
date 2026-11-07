"""Download a successful managed build's immutable result and verify before publishing."""
import argparse
import json
from pathlib import Path
import tempfile

import oci
from verify_release import validate_result


def fetch(devops, content, run_id, repository, version, output):
    if output.exists():
        raise ValueError('Output already exists')
    run = devops.get_build_run(run_id).data
    if run.lifecycle_state != 'SUCCEEDED':
        raise ValueError('Build has not succeeded')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='verified-build-', dir=output.parent) as directory:
        root = Path(directory)
        for name, limit in [('release.json', 128 * 1024), ('release.zip', 1024**3)]:
            response = content.get_generic_artifact_content_by_path(repository, name, version)
            total = 0
            with (root / name).open('xb') as stream:
                for chunk in response.data.raw.stream(1024 * 1024, decode_content=False):
                    total += len(chunk)
                    if total > limit:
                        raise ValueError('Artifact exceeds size limit')
                    stream.write(chunk)
            if name == 'release.json':
                metadata = json.loads((root / name).read_text())
                if metadata.get('build_id') != run_id:
                    raise ValueError('Artifact belongs to a different build run')
        metadata = validate_result(root)
        # Refuse to replace even an empty directory created concurrently.
        output.mkdir()
        try:
            for name in ('release.json', 'release.zip'):
                (root / name).rename(output / name)
        except BaseException:
            # Keep partial output visible for inspection; never report it verified.
            raise
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('region', 'run-id', 'repository-id', 'version'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--profile', default='DEFAULT')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    config = oci.config.from_file(profile_name=args.profile)
    config['region'] = args.region
    result = fetch(oci.devops.DevopsClient(config), oci.generic_artifacts_content.GenericArtifactsContentClient(config),
                   args.run_id, args.repository_id, args.version, args.output)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
