"""List the deployable entrypoint modules in a pinexq project.

An *entrypoint* module is one that serves a Step — it has an
``if __name__ == "__main__":`` block instantiating a Step subclass (e.g.
``HydrogenMainStep()``). A repo may carry several (e.g. a battery
``procon/main.py`` and a hydrogen ``procon/hydrogen_main.py``), each registering
its own family of function images that coexist on the cluster.

This is pure ``ast`` inspection — it does **not** import the modules (no
matplotlib / pinexq side effects), so it is safe to run in preflight. It scans
the directory of ``pinexq.toml``'s ``[project].entrypoint``.

Output: one ``<relpath>\\t<ClassName>`` per line, the toml default first (tagged
``(default)``). The deploy skill runs this in preflight and, when more than one
is found, **asks the user which to deploy**, then exports
``PROCON_ENTRYPOINT=<relpath>`` so every later step targets that module.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _procon import repo_root, pinexq_config  # noqa: E402


def _is_main_guard(test: ast.expr) -> bool:
    """True for ``__name__ == "__main__"``."""
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "__name__"
        and len(test.comparators) == 1
        and isinstance(test.comparators[0], ast.Constant)
        and test.comparators[0].value == "__main__"
    )


def served_step_class(path: Path) -> str | None:
    """The Step class instantiated in the module's ``__main__`` block, or None.

    Looks for ``<ClassName>(...)`` anywhere inside ``if __name__ == "__main__":``
    — that call is the serve entrypoint. Returns the bare class name.
    """
    try:
        tree = ast.parse(path.read_text())
    except (OSError, SyntaxError):
        return None
    for node in tree.body:
        if isinstance(node, ast.If) and _is_main_guard(node.test):
            for inner in ast.walk(node):
                if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name):
                    return inner.func.id
    return None


def main() -> None:
    root = repo_root()
    default = pinexq_config(root).get("project", {}).get("entrypoint", "")
    entry_dir = (root / default).resolve().parent if default else root

    found: list[tuple[str, str]] = []
    for py in sorted(entry_dir.glob("*.py")):
        if py.name.startswith("_"):
            continue
        cls = served_step_class(py)
        if cls:
            found.append((py.resolve().relative_to(root).as_posix(), cls))

    # Default entrypoint first, then alphabetical.
    found.sort(key=lambda t: (t[0] != default, t[0]))
    for rel, cls in found:
        tag = "\t(default)" if rel == default else ""
        print(f"{rel}\t{cls}{tag}")

    if len(found) > 1:
        print(
            f"\n{len(found)} entrypoints found — ASK THE USER which one to deploy, "
            f"then `export PROCON_ENTRYPOINT=<relpath>` for the rest of the run.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
