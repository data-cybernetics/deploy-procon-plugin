# deploy-procon (Claude Code plugin)

Repo-agnostic skill to deploy a pinexq ProCon: bump the project version, refresh
the lockfile, build/push/register the functions via the pinexq CLI, deprecate
the previous versions via `pinexq-client`, and tag each registered processing
step with its source (`GitHash=<sha>`, `Repository=<name>`). Driven entirely by the
target project's `pinexq.toml` + `pyproject.toml` — nothing is hardcoded to a
specific repo.

## Install

```
/plugin marketplace add <git-url-or-path-to-this-repo>
/plugin install deploy-procon@gramiangrid
```

Then, from any pinexq ProCon repo root, ask Claude to "deploy the ProCon" (or
run `/deploy-procon`). The skill walks the preflight → bump → relock → preview →
deploy → deprecate → commit → tag-git-hash runbook.

## Layout

```
.claude-plugin/
├── plugin.json        # plugin manifest
└── marketplace.json   # single-plugin marketplace (name: gramiangrid)
skills/deploy-procon/
├── SKILL.md           # the runbook
└── scripts/           # bump_version, list_functions, dump_signatures, deprecate_old, tag_git_hash, _procon
```

Script paths in `SKILL.md` resolve via `${CLAUDE_PLUGIN_ROOT}`.
