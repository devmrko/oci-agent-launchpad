"""Calculate the example travel allowance locally without starting a web server."""
import argparse
import json
from allowance import estimate


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("nights", type=int, help="숙박 일수 (1~14박)")
    args = parser.parse_args(argv)
    try:
        result = estimate(args.nights)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
