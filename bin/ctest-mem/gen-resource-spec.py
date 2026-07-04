#!/usr/bin/env python3
"""Write a CTest resource-spec file modeling RAM as an integer GB pool.

  gen-resource-spec.py --budget-gb 7 -o ci-mem-resources.json

Pass the result to ctest:  ctest -jN --resource-spec-file ci-mem-resources.json
Tests declare consumption via  RESOURCE_GROUPS "mem:<GB>"  (see gen-highmem-props.py).
CTest then guarantees the summed mem of concurrently running tests <= budget.
"""
import argparse
import json
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget-gb", type=int, required=True,
                    help="RAM budget in GB to expose as schedulable 'mem' slots")
    ap.add_argument("-o", "--output", default="-")
    args = ap.parse_args()

    spec = {
        "version": {"major": 1, "minor": 0},
        "local": [{"mem": [{"id": "0", "slots": args.budget_gb}]}],
    }
    text = json.dumps(spec, indent=2) + "\n"
    out = sys.stdout if args.output == "-" else open(args.output, "w")
    out.write(text)
    if out is not sys.stdout:
        out.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
