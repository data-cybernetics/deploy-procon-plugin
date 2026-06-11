#!/usr/bin/env python3
"""Bump the ProCon version (repo-agnostic).

Bumps ``[project].version`` in ``pyproject.toml`` — the universal source the
Docker build installs. If the project also keeps a version *mirror* next to its
entrypoint (a ``versions.py`` with ``pyproject_version = "..."`` — the
gramiangrid core/einhundert convention, stamped onto functions at runtime), that
file is bumped in lockstep and must already agree.

Usage:
    bump_version.py --show
    bump_version.py --bump {patch,minor,major}   # default: patch
    bump_version.py --set X.Y.Z
"""

import argparse
import re
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _procon import repo_root, entrypoint_dir  # noqa: E402

PYPROJECT_RE = re.compile(r'^(?P<pre>version\s*=\s*")(?P<ver>[^"]*)(?P<post>".*)$', re.M)
MIRROR_RE = re.compile(r'^(?P<pre>pyproject_version\s*=\s*")(?P<ver>[^"]*)(?P<post>".*)$', re.M)


def mirror_file(root: Path) -> Path | None:
    """A `versions.py` with `pyproject_version = "..."` beside the entrypoint, or None."""
    cand = entrypoint_dir(root) / "versions.py"
    if cand.is_file() and MIRROR_RE.search(cand.read_text()):
        return cand
    return None


def parse_semver(v: str) -> tuple[int, int, int]:
    parts = v.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        sys.exit(f"error: version {v!r} is not a plain X.Y.Z; use --set")
    return tuple(int(p) for p in parts)  # type: ignore[return-value]


def bumped(v: str, level: str) -> str:
    major, minor, patch = parse_semver(v)
    if level == "major":
        return f"{major + 1}.0.0"
    if level == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def rewrite(path: Path, pattern: re.Pattern, new: str) -> None:
    text = path.read_text()
    new_text, n = pattern.subn(lambda m: f"{m['pre']}{new}{m['post']}", text, count=1)
    if n != 1:
        sys.exit(f"error: could not rewrite the version in {path}")
    path.write_text(new_text)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--bump", choices=["patch", "minor", "major"])
    g.add_argument("--set", dest="explicit", metavar="X.Y.Z")
    ap.add_argument("--show", action="store_true", help="print current version and exit")
    args = ap.parse_args()

    root = repo_root()
    pyproject = root / "pyproject.toml"
    py_cur = tomllib.loads(pyproject.read_text())["project"]["version"]

    mirror = mirror_file(root)
    if mirror is not None:
        mir_cur = MIRROR_RE.search(mirror.read_text()).group("ver")
        if mir_cur != py_cur:
            sys.exit(f"error: version mirror out of sync — pyproject.toml={py_cur!r} but "
                     f"{mirror.relative_to(root)}={mir_cur!r}. Reconcile before bumping.")

    if args.show:
        print(py_cur)
        return

    target = args.explicit if args.explicit else bumped(py_cur, args.bump or "patch")
    parse_semver(target)
    if parse_semver(target) <= parse_semver(py_cur):
        sys.exit(f"error: target {target} is not greater than current {py_cur}")

    rewrite(pyproject, PYPROJECT_RE, target)
    if mirror is not None:
        rewrite(mirror, MIRROR_RE, target)
        print(f"{py_cur} -> {target}  (pyproject.toml + {mirror.relative_to(root)})")
    else:
        print(f"{py_cur} -> {target}  (pyproject.toml)")


if __name__ == "__main__":
    main()
