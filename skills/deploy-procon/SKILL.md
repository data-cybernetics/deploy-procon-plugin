---
name: deploy-procon
description: >-
  Deploy a pinexq ProCon from the current repo. Bumps the project version,
  refreshes the lockfile, builds/pushes/registers the functions via the pinexq
  CLI, then deprecates the previous versions of each deployed function via
  pinexq-client. Repo-agnostic: driven by the project's pinexq.toml + pyproject.toml.
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
**BuildKit secrets**, then deploy:
```bash
set -a; [ -f .env ] && . ./.env; set +a   # PINEXQ_API_KEY + any UV_INDEX_* creds
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

## Notes
- **Entrypoint discovery.** Scripts import the module at `pinexq.toml`'s
  `entrypoint` and pick the most-derived `pinexq.procon.step.Step` subclass
  defined there. If ambiguous, set `PROCON_STEP=<ClassName>`.
- **Version source.** `pyproject.toml` is the source of truth. The optional
  `versions.py` mirror is a convention some projects use to stamp the version
  onto functions at runtime; projects that prefer a single source can read
  `importlib.metadata.version(pkg)` instead and drop the mirror.
- **Project vs user scope.** This skill is repo-agnostic and intended to live at
  user level (`~/.claude/skills/deploy-procon/`). A project may still ship its
  own `.claude/skills/deploy-procon/`, which shadows this one in that repo.
