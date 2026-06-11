#!/usr/bin/env python3
"""Dump the function-registration manifests the deploy would upload (repo-agnostic).

The "what would register" debug path: builds the exact payload that
``pinexq register`` / ``pinexq deploy`` uploads per function
(``get_function_model().model_dump(by_alias=True)`` — name, version,
parameter/return JSON schemas, input/output dataslots) for the entrypoint Step
declared in pinexq.toml. Offline: no Docker, no package index, no network.

Usage:
    dump_signatures.py                 # all exposed functions, to stdout
    dump_signatures.py --function NAME # just one
    dump_signatures.py --out DIR       # write <name>.json per function
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
    ap.add_argument("--function", help="dump only this function (default: all exposed)")
    ap.add_argument("--out", type=Path, help="write <name>.json per function into this dir")
    args = ap.parse_args()

    warnings.filterwarnings("ignore", message="Usage of dataslot")
    step = load_entrypoint_step(repo_root())

    names = [args.function] if args.function else sorted(step._signatures)
    missing = [n for n in names if n not in step._signatures]
    if missing:
        sys.exit(f"error: unknown function(s) {missing}. Available: {sorted(step._signatures)}")

    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
    for name in names:
        manifest = step._signatures[name].get_function_model().model_dump(by_alias=True)
        text = json.dumps(manifest, indent=2, default=str, sort_keys=True)
        if args.out:
            path = args.out / f"{name}.json"
            path.write_text(text + "\n")
            print(f"wrote {path}")
        else:
            print(f"===== {name} =====")
            print(text)


if __name__ == "__main__":
    main()
