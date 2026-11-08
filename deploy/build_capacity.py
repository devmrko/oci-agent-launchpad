"""Check all build paths together, grouping shared filesystems before work."""
import argparse
import json
import math
import shutil
from pathlib import Path

from capacity_plan import calculate, GIB


def preflight(entries):
    if not isinstance(entries, list) or not entries:
        raise ValueError('Build storage entries required')
    groups = {}
    seen = set()
    for entry in entries:
        path = Path(entry['path']).resolve(strict=True)
        if not path.is_dir() or str(path) in seen:
            raise ValueError('Unique existing storage directories required')
        seen.add(str(path))
        budget = calculate(entry['plan'])
        device = path.stat().st_dev
        group = groups.setdefault(device, {'paths': [], 'resident_gib': 0, 'additional_gib': 0, 'reserve_gib': 0})
        group['paths'].append(str(path))
        group['resident_gib'] += budget['components_gib']['resident']
        group['additional_gib'] += budget['components_gib']['growth'] + budget['components_gib']['transient']
        # A common filesystem needs one reserve, at least the largest requested.
        group['reserve_gib'] = max(group['reserve_gib'], budget['reserve_gib'])
    reports = []
    for group in groups.values():
        usage = shutil.disk_usage(group['paths'][0])
        required_free = group['additional_gib'] + group['reserve_gib']
        required_total = math.ceil(group['resident_gib'] + required_free)
        reports.append({**group, 'required_free_gib': required_free,
                        'required_filesystem_gib': required_total,
                        'free_gib': usage.free / GIB, 'total_gib': usage.total / GIB,
                        'result': 'PASS' if usage.free >= required_free * GIB and usage.total >= required_total * GIB else 'INSUFFICIENT'})
    return {'result': 'PASS' if all(r['result'] == 'PASS' for r in reports) else 'INSUFFICIENT',
            'filesystems': reports}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    report = preflight(json.loads(args.config.read_text())['storage'])
    print(json.dumps(report, indent=2))
    if report['result'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
