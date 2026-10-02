# Contributor instructions

Read `README.md`, then the current documents and code relevant to the task.
Check Git status and diffs first; preserve unrelated work.

## Changes

- Keep changes focused. Prefer existing dependencies and direct code; discuss
  architecture or dependency changes that exceed the requested scope.
- Keep documentation concise, with each fact in its owning document.
- Preserve the timing and persistence contracts in `docs/ARCHITECTURE.md`
  unless the request changes them; update tests and documentation together.

## Data and interface

- Original recordings are read-only. Never repair, reindex, rename, delete or
  write beside them. Open source SQLite read-only and immutable where supported;
  never use a write probe on source storage.
- Keep source and derived paths separate and contained. Do not follow source
  symlinks. Publish only validated, identity-matching artifacts; preserve valid
  output when replacement fails.
- Render backend text safely. Preserve accessible controls, keyboard focus and
  reduced motion. Loading, failure and progress states must be truthful.
- Use muted text for single-line loading and empty states. Never overlay loading
  messages on visible data.
- Keep recordings, generated data, credentials, private configuration, database
  dumps and operational inventories out of Git.

## Verification and delivery

- Use synthetic fixtures for routine tests. Run relevant checks; do not weaken
  behavioral tests to make changes pass.
- Real-source checks need a defined target, bounded scope and lightweight
  before/after inventories. Do not hash large payloads unnecessarily.
- Repository changes do not imply deployment. Follow `docs/OPERATIONS.md` for
  VM work and resolve the target, interruption and recovery before changes.
- Follow existing authorization. Ask only about missing decisions or actions
  outside the requested scope, especially destructive changes or public access.
- Use descriptive commits and preserve shared history and deployment commit IDs.
  Commit, push and deploy only within the user's requested scope.
- At handoff, report changes, checks, limitations and Git state. Distinguish
  observed results from assumptions and user reports.
