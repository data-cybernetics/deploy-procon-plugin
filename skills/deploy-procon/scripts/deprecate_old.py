#!/usr/bin/env python3
"""Deprecate superseded versions of the deployed functions (repo-agnostic).

After a deploy registers every function at the current version, the previous
versions of those same names should be deprecated. The pinexq CLI can't do this,
so we use pinexq-client.

For each function the entrypoint exposes, query all non-deprecated versions and
deprecate every one whose version differs from the one the entrypoint currently
stamps. Names come from the entrypoint Step, so deprecation only ever touches
this project's own registrations.

DRY-RUN BY DEFAULT — prints what it would deprecate. Pass --apply to mutate.

Usage:
    deprecate_old.py
    deprecate_old.py --apply
    deprecate_old.py --reason "..."
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _procon import repo_root, load_entrypoint_step, build_client, project_name  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="actually deprecate (default: dry run)")
    ap.add_argument("--reason", default=None, help="deprecation reason")
    args = ap.parse_args()

    import warnings
    warnings.filterwarnings("ignore", message="Usage of dataslot")

    from pinexq.client.job_management.model import FunctionNameMatchTypes
    from pinexq.client.job_management.tool import ProcessingStepQuery

    root = repo_root()
    step = load_entrypoint_step(root)
    # (function name -> the version this image registers it at)
    current = {name: schema.version for name, schema in step._signatures.items()}
    client = build_client(root)
    reason = args.reason or f"superseded by {project_name(root)} deploy"

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"[{mode}] {len(current)} function(s); reason: {reason!r}\n")

    to_deprecate: list[tuple[str, str]] = []
    failures: list[tuple[str, str, str]] = []
    for name, keep_version in sorted(current.items()):
        query = ProcessingStepQuery.create(
            client,
            function_name=name,
            function_name_match_type=FunctionNameMatchTypes.match_exact,
            version=None,
            show_deprecated=False,
            # None = all versions (stable + prerelease). NB: this API treats
            # show_prerelease=True as "only prereleases", so it would hide
            # stable versions and find nothing to deprecate.
            show_prerelease=None,
        )
        for ps in query.iter():
            ver = ps.processing_step_hco.version
            if ver == keep_version:
                continue
            to_deprecate.append((name, ver))
            if args.apply:
                try:
                    ps.deprecate(reason=reason)
                    print(f"  deprecated {name}:{ver}")
                except Exception as ex:  # isolate per-step failures
                    failures.append((name, ver, str(ex)))
                    print(f"  FAILED     {name}:{ver} -> {ex}")
            else:
                print(f"  would deprecate {name}:{ver}  (keeping {keep_version})")

    print()
    if not to_deprecate:
        print("nothing to deprecate — registry already clean.")
    elif args.apply:
        ok = len(to_deprecate) - len(failures)
        print(f"deprecated {ok}/{len(to_deprecate)}" + (f"; {len(failures)} failed" if failures else ""))
    else:
        print(f"{len(to_deprecate)} version(s) would be deprecated. Re-run with --apply.")

    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
