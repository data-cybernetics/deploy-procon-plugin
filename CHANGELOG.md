# Changelog

All notable changes to the deploy-procon plugin are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/); versions
refer to the plugin version in `.claude-plugin/plugin.json`.

## [1.1.0] - 2026-07-02

### Added
- `scripts/tag_git_hash.py` and runbook step 8: after the commit decision,
  every just-registered processing step is tagged with its source —
  `GitHash=<sha>` (with a `-dirty` suffix when the working tree has
  uncommitted changes) and `Repository=<name>` (basename of the `origin`
  remote URL, falling back to the repo directory name). Preserves the steps'
  other tags, replaces stale `GitHash=`/`Repository=` tags, idempotent;
  supports `--dry-run` and `--hash`/`--repository` overrides.
- Entrypoint selection (landed 2026-06-23 without a version bump):
  `scripts/list_entrypoints.py` discovers every entrypoint Step in the repo
  by `ast` inspection, and when there is more than one the skill asks the
  user which to deploy. The answer is carried in `PROCON_ENTRYPOINT`, which
  steers the version mirror, preview, build/register (via a temporary
  `pinexq.toml` swap), and deprecation.

## [1.0.0] - 2026-06-11

### Added
- Initial release: the repo-agnostic deploy-procon skill packaged as a Claude
  Code plugin with a single-plugin marketplace (`gramiangrid`).
- Runbook: preflight → version bump → lockfile refresh → offline registration
  preview → `pinexq deploy` (BuildKit secrets for private indexes) →
  deprecate previous versions → offer to commit.
- Helper scripts: `bump_version.py`, `list_functions.py`,
  `dump_signatures.py`, `deprecate_old.py`, shared `_procon.py`.
