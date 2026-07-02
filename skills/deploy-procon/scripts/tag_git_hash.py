#!/usr/bin/env python3
"""Tag the deployed processing steps with their source repo + commit (repo-agnostic).

For each function the entrypoint exposes, find the processing step registered
at the current version on the endpoint and set two tags on it:

- ``GitHash=<sha>`` — the deploying commit. When the working tree has
  uncommitted changes the hash gets a ``-dirty`` suffix, since HEAD alone
  doesn't describe what was deployed — commit first (the skill tags after the
  commit step) to get a clean hash.
- ``Repository=<name>`` — the git repository name (basename of the ``origin``
  remote URL, falling back to the repo root directory name).

Existing tags are preserved; previous ``GitHash=...`` / ``Repository=...``
tags are replaced.

Names and versions come from the entrypoint Step, so tagging only ever touches
this project's own registrations. Idempotent.

Usage:
    tag_git_hash.py
    tag_git_hash.py --dry-run
    tag_git_hash.py --hash <sha>          # override the commit value (skips git)
    tag_git_hash.py --repository <name>   # override the repository value
"""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _procon import repo_root, load_entrypoint_step, build_client  # noqa: E402

MANAGED_KEYS = ("GitHash", "Repository")


def git_hash(root: Path) -> str:
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                          capture_output=True, text=True)
    if head.returncode != 0:
        sys.exit(f"error: cannot resolve git HEAD in {root}: {head.stderr.strip()}")
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=root,
                           capture_output=True, text=True).stdout.strip()
    return head.stdout.strip() + ("-dirty" if dirty else "")


def repository_name(root: Path) -> str:
    url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=root,
                         capture_output=True, text=True)
    if url.returncode == 0 and url.stdout.strip():
        name = url.stdout.strip().rstrip("/").rsplit("/", 1)[-1]
        name = name.removesuffix(".git")
        # ssh shorthand without a path slash, e.g. git@host:repo.git
        name = name.rsplit(":", 1)[-1]
        if name:
            return name
    return root.name


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="print what would be tagged, don't mutate")
    ap.add_argument("--hash", default=None, help="GitHash value override (default: git rev-parse HEAD, '-dirty' appended if the tree is dirty)")
    ap.add_argument("--repository", default=None, help="Repository value override (default: basename of the origin remote URL, else the repo directory name)")
    args = ap.parse_args()

    import warnings
    warnings.filterwarnings("ignore", message="Usage of dataslot")

    from pinexq.client.job_management.model import FunctionNameMatchTypes
    from pinexq.client.job_management.tool import ProcessingStepQuery

    root = repo_root()
    new_tags = [
        f"GitHash={args.hash or git_hash(root)}",
        f"Repository={args.repository or repository_name(root)}",
    ]
    step = load_entrypoint_step(root)
    # (function name -> the version this image registers it at)
    current = {name: schema.version for name, schema in step._signatures.items()}
    client = build_client(root)

    mode = "DRY RUN" if args.dry_run else "APPLY"
    print(f"[{mode}] tagging {len(current)} step(s) with {new_tags}\n")
    if new_tags[0].endswith("-dirty"):
        print("  note: working tree is dirty — commit the version bump first for a clean hash\n")

    missing: list[str] = []
    failures: list[tuple[str, str, str]] = []
    for name, version in sorted(current.items()):
        query = ProcessingStepQuery.create(
            client,
            function_name=name,
            function_name_match_type=FunctionNameMatchTypes.match_exact,
            version=version,
            show_deprecated=False,
            show_prerelease=None,  # None = all versions (see deprecate_old.py)
        )
        found = False
        for ps in query.iter():
            if ps.processing_step_hco.version != version:
                continue  # belt-and-braces on top of the server-side filter
            found = True
            existing = ps.processing_step_hco.tags or []
            kept = [t for t in existing
                    if not t.startswith(tuple(f"{k}=" for k in MANAGED_KEYS))]
            if set(existing) == set(kept) | set(new_tags):
                print(f"  ok      {name}:{version} already tagged")
                continue
            if args.dry_run:
                print(f"  would tag {name}:{version}  (tags: {existing} -> {kept + new_tags})")
                continue
            try:
                ps.set_tags(kept + new_tags)
                print(f"  tagged  {name}:{version}")
            except Exception as ex:  # isolate per-step failures
                failures.append((name, version, str(ex)))
                print(f"  FAILED  {name}:{version} -> {ex}")
        if not found:
            missing.append(f"{name}:{version}")
            print(f"  MISSING {name}:{version} — not registered on the endpoint (deploy first?)")

    print()
    if missing or failures:
        if missing:
            print(f"{len(missing)} step(s) not found: {', '.join(missing)}")
        if failures:
            print(f"{len(failures)} step(s) failed to tag")
        sys.exit(1)
    print("all steps tagged." if not args.dry_run else "dry run complete. Re-run without --dry-run to apply.")


if __name__ == "__main__":
    main()
