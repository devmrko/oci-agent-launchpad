"""Plan filesystem capacity before provisioning; check free space before work."""
import argparse
import json
import math
import shutil
from pathlib import Path

GIB = 1024 ** 3


def amount(data, key):
    value = data.get(key)
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError(f'{key} must be a finite non-negative number')
    return value


def calculate(plan):
    if plan.get('schema_version') != 1:
        raise ValueError('Unsupported capacity plan')
    if not isinstance(plan.get('role'), str) or not plan['role'].strip():
        raise ValueError('Role required')
    components = plan.get('components')
    if not isinstance(components, list) or not components:
        raise ValueError('Explicit capacity components required')
    totals = {'resident': 0.0, 'growth': 0.0, 'transient': 0.0}
    names = set()
    for component in components:
        name = component.get('name')
        if not isinstance(name, str) or not name or name in names:
            raise ValueError('Unique component names required')
        names.add(name)
        phase = component.get('phase')
        if phase not in totals or not isinstance(component.get('basis'), str) or not component['basis'].strip():
            raise ValueError('Each component needs a phase and measurement/estimate basis')
        copies = component.get('copies')
        if type(copies) is not int or copies < 1:
            raise ValueError('copies must be a positive integer')
        totals[phase] += amount(component, 'gib') * copies
    reserve = amount(plan, 'reserve_gib')
    if reserve == 0:
        raise ValueError('Explicit positive reserve required')
    peak = sum(totals.values()) + reserve
    # Resident means already present at execution time, not another download.
    additional = totals['growth'] + totals['transient'] + reserve
    return {'role': plan['role'], 'components_gib': totals, 'reserve_gib': reserve,
            'required_filesystem_gib': math.ceil(peak),
            'required_free_gib': additional}


def check(plan, path):
    result = calculate(plan)
    usage = shutil.disk_usage(path)
    result.update(path=str(Path(path).resolve()), total_gib=usage.total / GIB, free_gib=usage.free / GIB)
    result['result'] = 'PASS' if (
        usage.total >= result['required_filesystem_gib'] * GIB
        and usage.free >= result['required_free_gib'] * GIB
    ) else 'INSUFFICIENT'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--path', type=Path, help='Existing path on the actual target filesystem')
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    result = check(plan, args.path) if args.path else calculate(plan)
    print(json.dumps(result, indent=2))
    if result.get('result') == 'INSUFFICIENT':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
