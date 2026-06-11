#!/usr/bin/env python3
"""List the functions the ProCon will register, with versions (repo-agnostic).

Imports the entrypoint Step declared in pinexq.toml and reads its signatures.
Offline, no network, no mutation.

Usage: list_functions.py [--json]
"""

import argparse
import json
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _procon import repo_root, load_entrypoint_step  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args()

    warnings.filterwarnings("ignore", message="Usage of dataslot")
    step = load_entrypoint_step(repo_root())
    funcs = {name: schema.version for name, schema in step._signatures.items()}

    if args.json:
        print(json.dumps(funcs, indent=2, sort_keys=True))
        return
    width = max((len(n) for n in funcs), default=0)
    for name in sorted(funcs):
        print(f"{name:<{width}}  {funcs[name]}")
    print(f"\n{len(funcs)} functions")


if __name__ == "__main__":
    main()
