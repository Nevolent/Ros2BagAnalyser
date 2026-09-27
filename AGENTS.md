# Contributor instructions

ROS 2 Bag Analyser is a deployed engineering application. Read `README.md`, then
only the current documents and code relevant to the task. `docs/history/`
contains superseded reference material, not active instructions.

## Working method

- Work from the user's request. There are no building-block prompts, mandatory
  phase approvals, or exact-command ceremonies for routine repository work.
- Check Git status and relevant diffs first; preserve unrelated local work.
- Keep changes focused and understandable. Prefer direct code and existing
  dependencies; discuss substantial architecture or dependency changes when
  they exceed the requested work.
- Keep documentation short and put each fact in its owning document. Update
  current guidance when behavior changes instead of adding another status log.

## Data and application care

- Original recordings are read-only. Never repair, reindex, rename, delete, or
  write beside them. Open source SQLite explicitly read-only and immutable
  where supported; never use a write probe on source storage.
- Keep source and derived paths separate and contained. Do not follow source
  symlinks. Publish only validated, identity-matching artifacts; preserve valid
  output when a replacement fails.
- Preserve the timing and persistence behavior documented in
  `docs/ARCHITECTURE.md` unless the requested change intentionally revises it.
  Update the corresponding tests and documentation together.
- Use muted secondary text for single-line loading and empty states. Never overlay
  a loading message on already visible data.
- Render backend text safely. Keep accessible controls, keyboard focus,
  reduced-motion behavior, and truthful loading, failure, and progress states.
- Keep recordings, generated artifacts, credentials, private configuration,
  database dumps, and operational inventories out of Git.

## Verification and live work

- Use synthetic fixtures for routine tests. Run checks appropriate to the
  change; do not weaken behavioral tests to make a change pass.
- Real-source checks need a defined target and bounded scope, with lightweight
  before/after inventories. Do not hash large source payloads unnecessarily.
- Repository work does not imply a live deployment. Use `docs/OPERATIONS.md`
  for VM work; resolve the target, interruption, and recovery before changes.
- Follow existing user authorization. Ask only for missing decisions or actions
  outside it, especially destructive changes or public exposure.

## Git and handoff

- Use descriptive commits. Preserve shared history and deployment commit IDs;
  use a normal follow-up commit unless a history rewrite is specifically needed.
- Commit, push, and deploy according to the user's requested scope. A local
  commit does not imply permission to publish or update the VM.
- At handoff, summarize the change, checks actually run, limitations, and Git
  state. Distinguish observed results from user reports and unverified assumptions.
