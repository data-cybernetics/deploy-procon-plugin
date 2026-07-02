---
name: deploy-procon
description: >-
  Deploy a pinexq ProCon from the current repo. Bumps the project version,
  refreshes the lockfile, builds/pushes/registers the functions via the pinexq
  CLI, deprecates the previous versions of each deployed function via
  pinexq-client, and tags each registered processing step with its source
  (GitHash=..., Repository=...). Repo-agnostic: driven by the project's pinexq.toml + pyproject.toml.
  Use when asked to deploy, release, publish, or ship a ProCon / its functions,
  or to "bump and deploy".
---

# Deploy a pinexq ProCon

This skill works for **any** pinexq ProCon repo — it reads the project's
`pinexq.toml` (name, endpoint, **entrypoint**) and `pyproject.toml` (version),
and introspects whatever Step the entrypoint declares. Nothing is hardcoded to a
specific project.

Run all steps from the **repo root** of the project you're deploying. `uv` must
be available (often at `/usr/local/uv`; `export PATH="/usr/local:$PATH"`). The
helper scripts live in `scripts/` next to this file; invoke them with
`uv run python "$S/scripts/<name>.py"` **from the target repo** so they use that
repo's environment. Below, `$S` = the directory containing this SKILL.md. When
this skill runs as a plugin, set it once per session before the commands:

```bash
S="${CLAUDE_PLUGIN_ROOT}/skills/deploy-procon"
```

## Procedure

### 1. Preflight
- Confirm the cwd is a pinexq project root (`pinexq.toml` + `pyproject.toml`
  present). The scripts exit with a clear message otherwise.
- Confirm credentials: `PINEXQ_API_KEY` (+ `PINEXQ_BASE_URL`) in the environment
  or a repo-root `.env`. If missing, STOP and ask the user to set them.
- `git status`: if dirty, mention it; let the user decide whether to continue.
- **Pick the entrypoint to deploy.** A repo can carry several entrypoint Steps
  in separate modules (e.g. a battery `procon/main.py` and a hydrogen
  `procon/hydrogen_main.py`), each registering its own family of function images
  that coexist on the cluster. List them:
  ```bash
  uv run python "$S/scripts/list_entrypoints.py"   # <relpath>\t<ClassName>, default tagged
  ```
  - **One entrypoint** → use it (the `pinexq.toml` default); continue.
  - **More than one** → **ASK THE USER which one to deploy** — this is the
    interface; do not silently default and do not make them set an env var by
    hand. Present the discovered modules as the options. Then, for the chosen
    one, `export PROCON_ENTRYPOINT="<its relpath>"` so every later step (version
    mirror, preview, build/register, deprecate) targets it. Leave
    `PROCON_ENTRYPOINT` unset only when the choice is the toml default.

### 2. Choose and bump the version
```bash
uv run python "$S/scripts/bump_version.py" --show
uv run python "$S/scripts/bump_version.py" --bump patch   # or --set X.Y.Z
```
Bumps `[project].version` in `pyproject.toml`. If the project keeps a version
mirror beside its entrypoint (a `versions.py` with `pyproject_version = "..."` —
e.g. the gramiangrid convention, stamped onto functions at runtime), it is
bumped in lockstep and must already agree. Confirm the target with the user.

### 3. Refresh the lockfile
The Docker build uses `uv sync --locked`, so the new version must be in the lock:
```bash
uv lock && uv sync
```

### 4. Preview what will register
```bash
uv run python "$S/scripts/list_functions.py"                 # names + versions
uv run python "$S/scripts/dump_signatures.py"                # full manifests (offline)
```
`dump_signatures.py` builds the exact payload `register`/`deploy` uploads — names,
versions, parameter/return schemas, dataslots — with no Docker or network. Show
it to the user and confirm the versions are the new ones.

### 5. Deploy (build + push + register)
Load credentials from `.env` and forward any private-index credentials as
**BuildKit secrets**, then deploy. Run this as a **single** Bash invocation so
the `PROCON_ENTRYPOINT` swap restores `pinexq.toml` even if the deploy fails:
```bash
set -a; [ -f .env ] && . ./.env; set +a   # PINEXQ_API_KEY + any UV_INDEX_* creds

# PROCON_ENTRYPOINT: pinexq deploy reads pinexq.toml's [project].entrypoint, so
# temporarily point it at the override for the build, then always restore. No-op
# when PROCON_ENTRYPOINT is unset.
if [ -n "${PROCON_ENTRYPOINT:-}" ]; then
  cp pinexq.toml pinexq.toml.deploybak
  trap 'mv -f pinexq.toml.deploybak pinexq.toml' EXIT
  python3 - "$PROCON_ENTRYPOINT" <<'PY'
import re, sys, pathlib
p = pathlib.Path("pinexq.toml")
p.write_text(re.sub(r'(?m)^(\s*entrypoint\s*=\s*).*$', r'\1"%s"' % sys.argv[1], p.read_text(), count=1))
PY
fi

# forward every UV_INDEX_* var as a build secret (id = lowercased var name)
args=()
while IFS= read -r v; do
  id="$(printf '%s' "$v" | tr '[:upper:]' '[:lower:]')"
  args+=(--secret "id=$id,env=$v")
done < <(env | grep -oE '^UV_INDEX_[A-Z0-9_]+' | sort -u)
uvx --from pinexq-cli --prerelease=allow pinexq deploy --verbose "${args[@]}"
```
- Endpoint comes from `pinexq.toml`; API key from `PINEXQ_API_KEY`. Builds and
  pushes an OCI image (needs Docker + push access) — takes a while. Scope with
  repeated `-f <name>`.
- **Different entrypoint?** Export `PROCON_ENTRYPOINT=<module path>` before this
  step (see Notes) — the swap above points the build at it and restores the toml
  on exit. The same env var already steers steps 2/4/6 directly.
- **Never echo the secret values.** Load `.env` into the env and pass vars by
  *name* (`--secret id=...,env=VAR`); BuildKit mounts them only during `uv sync`
  (never in an image layer or `docker history`). Ensure `.env` is in
  `.dockerignore` so the build context doesn't bake it into the image.
- **Private-index auth.** If a dep resolves from a private `[[tool.uv.index]]`,
  the Docker build's `uv sync --locked` needs that index's credentials. Put them
  in `.env` as uv's per-index vars `UV_INDEX_<NAME>_USERNAME` /
  `UV_INDEX_<NAME>_PASSWORD` (`<NAME>` = the index name upper-cased, `-`→`_`;
  token registries use username `__token__`). The loop above forwards them; the
  project's `Dockerfile` must mount them on the `uv sync` step, e.g.
  `--mount=type=secret,id=uv_index_<name>_username` and `..._password`, exporting
  them as the matching `UV_INDEX_*` env vars for that `RUN`.
- **Local-path deps don't build.** If `[tool.uv.sources]` pins a dep to a local
  `../path`, `uv sync --locked` fails in the build (outside the context).
  Publish it to the index and switch its source to `{ index = ... }` first;
  until then, use step 4 to validate registration offline.

### 6. Deprecate the previous versions
Dry-run first, show the user, apply on confirmation:
```bash
uv run python "$S/scripts/deprecate_old.py"            # dry run
uv run python "$S/scripts/deprecate_old.py" --apply    # after confirmation
```
Deprecates every non-current version of each function the entrypoint exposes.
Scoped to this project's own function names; idempotent.

### 7. Offer to commit
Offer to commit the version bump (`pyproject.toml`, any mirror, `uv.lock`).
Never commit without the user asking.

### 8. Tag the registered steps with the git hash and repo name
After the commit decision, stamp every just-registered processing step with
`GitHash=<sha>` and `Repository=<name>` tags so the deployed code is traceable
to its source:
```bash
uv run python "$S/scripts/tag_git_hash.py"
```
Runs after step 7 on purpose: once the bump is committed, HEAD is the commit
that contains the deployed version. If the user declined to commit (or the tree
is otherwise dirty), the hash gets a `-dirty` suffix — mention that. The repo
name comes from the `origin` remote URL (fallback: the repo directory name).
Preserves the steps' other tags, replaces any previous `GitHash=`/`Repository=`
tags, and is idempotent; scoped to this project's own function names at their
current versions.

## Notes
- **Entrypoint discovery.** Scripts import the module at `pinexq.toml`'s
  `entrypoint` and pick the most-derived `pinexq.procon.step.Step` subclass
  defined there. If ambiguous, set `PROCON_STEP=<ClassName>`.
- **Multiple entrypoints (the interface is a question).** `list_entrypoints.py`
  finds every entrypoint module (an `if __name__ == "__main__":` block serving a
  Step) by `ast` inspection — no imports. When it finds more than one, the skill
  **asks the user which to deploy** (step 1) rather than defaulting or making
  them set anything by hand. `PROCON_ENTRYPOINT` is just the carrier for that
  answer: exported once, it overrides `pinexq.toml`'s `[project].entrypoint` for
  the whole run via `resolved_entrypoint` (steps 2/4/6) and via step 5's
  temporary-toml swap (the `pinexq deploy` CLI reads the toml). Combine with
  `PROCON_STEP` only if the chosen module itself defines more than one Step.
- **Version source.** `pyproject.toml` is the source of truth. The optional
  `versions.py` mirror is a convention some projects use to stamp the version
  onto functions at runtime; projects that prefer a single source can read
  `importlib.metadata.version(pkg)` instead and drop the mirror.
- **Project vs user scope.** This skill is repo-agnostic and intended to live at
  user level (`~/.claude/skills/deploy-procon/`). A project may still ship its
  own `.claude/skills/deploy-procon/`, which shadows this one in that repo.
