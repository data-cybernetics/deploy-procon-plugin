"""Shared helpers for the deploy-procon skill — repo-agnostic.

Everything is driven by the two standard pinexq project files in the current
working directory: ``pinexq.toml`` (name, endpoint, entrypoint) and
``pyproject.toml`` (version). No project is hardcoded; run the skill from any
pinexq ProCon repo root.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tomllib
from pathlib import Path


def repo_root() -> Path:
    """Nearest ancestor of the CWD that has both pinexq.toml and pyproject.toml."""
    for d in [Path.cwd(), *Path.cwd().parents]:
        if (d / "pinexq.toml").is_file() and (d / "pyproject.toml").is_file():
            return d
    sys.exit("error: run this from a pinexq project root (needs pinexq.toml + pyproject.toml)")


def pinexq_config(root: Path) -> dict:
    return tomllib.loads((root / "pinexq.toml").read_text())


def project_name(root: Path) -> str:
    return pinexq_config(root).get("project", {}).get("name", root.name)


def entrypoint_dir(root: Path) -> Path:
    """Directory containing the entrypoint module (e.g. .../procon)."""
    entry = pinexq_config(root).get("project", {}).get("entrypoint", "")
    return (root / entry).resolve().parent


def load_entrypoint_step(root: Path):
    """Import the Step declared as ``pinexq.toml``'s entrypoint and return an
    instance built with ``use_cli=False``.

    The deployed class is taken to be the most-derived ``pinexq.procon.step.Step``
    subclass *defined in* the entrypoint module. If that's ambiguous, set
    ``PROCON_STEP=<ClassName>`` to disambiguate.
    """
    cfg = pinexq_config(root)
    entry = cfg.get("project", {}).get("entrypoint")
    if not entry:
        sys.exit("error: pinexq.toml has no [project].entrypoint")
    entry_path = (root / entry).resolve()
    if not entry_path.is_file():
        sys.exit(f"error: entrypoint module not found: {entry_path}")

    # Make the project importable (src-layout or flat) so the module's absolute
    # imports resolve.
    for p in (root / "src", root):
        if p.is_dir() and str(p) not in sys.path:
            sys.path.insert(0, str(p))

    from pinexq.procon.step import Step

    spec = importlib.util.spec_from_file_location("_procon_entrypoint", entry_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    defined = [
        obj for obj in vars(module).values()
        if isinstance(obj, type) and issubclass(obj, Step) and obj is not Step
        and obj.__module__ == module.__name__
    ]
    candidates = defined or [
        obj for obj in vars(module).values()
        if isinstance(obj, type) and issubclass(obj, Step) and obj is not Step
    ]
    if not candidates:
        sys.exit(f"error: no pinexq Step subclass found in {entry_path}")

    override = os.environ.get("PROCON_STEP")
    if override:
        match = [c for c in candidates if c.__name__ == override]
        if not match:
            sys.exit(f"error: PROCON_STEP={override!r} not among "
                     f"{[c.__name__ for c in candidates]}")
        step_cls = match[0]
    else:
        # most-derived = not a base class of any other candidate
        leaves = [c for c in candidates
                  if not any(o is not c and issubclass(o, c) for o in candidates)]
        if len(leaves) != 1:
            names = [c.__name__ for c in (leaves or candidates)]
            sys.exit(f"error: cannot uniquely pick the entrypoint Step among {names}; "
                     f"set PROCON_STEP=<ClassName>")
        step_cls = leaves[0]

    return step_cls(use_cli=False)


def build_client(root: Path):
    """A pinexq httpx client from PINEXQ_BASE_URL / PINEXQ_API_KEY (env or repo .env)."""
    import httpx

    base = os.environ.get("PINEXQ_BASE_URL")
    key = os.environ.get("PINEXQ_API_KEY")
    if not (base and key):
        env = root / ".env"
        if env.is_file():
            try:
                from dotenv import load_dotenv
                load_dotenv(env)
            except ImportError:
                for line in env.read_text().splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        base = base or os.environ.get("PINEXQ_BASE_URL")
        key = key or os.environ.get("PINEXQ_API_KEY")
    if not (base and key):
        sys.exit("error: set PINEXQ_BASE_URL and PINEXQ_API_KEY (environment or repo-root .env)")
    if not base.startswith(("http://", "https://")):
        base = "https://" + base
    return httpx.Client(base_url=base, headers={"x-api-key": key}, timeout=60.0)
