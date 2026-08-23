# AGENTS.md

## Purpose

This file contains the active standing instructions for Codex and other
automated contributors working on ROS 2 Bag Analyser V1.

V0 is complete. Its historical contracts and evidence are frozen under
`docs/v0/`. Do not rewrite that evidence to make V1 appear older or more
complete than it is.

The static files under `archive/` are the user-authored V1 frontend reference.
They contain mock data, but their design and interaction flow are intentional.
Do not treat them as disposable generated output or redesign them for
convenience.

## Current status

The V1 product, architecture, roadmap, and detailed building-block prompts were
approved on 2026-08-04. Building block 1 was accepted on the same date.
Building block 2 was then implemented, verified, and accepted. A separately
approved smooth front-camera corrective slice was implemented synthetically as
part of the accumulated pre-overhaul baseline. An approved moved-path catalog correction now
keeps retained missing history out of ordinary current catalog projections. A
separately approved move-aware artifact-reuse correction preserves compatible
processed output across unambiguous folder moves. Building block 3 was invoked
on 2026-08-16. Its repository-readiness phase is implemented and locally
verified. On 2026-08-23 the user accepted all preceding application and
repository-readiness work as the working pre-overhaul baseline and authorized
its Git checkpoint and push. Prompt 2A, the big UI overhaul and real
processing-controls correction, is approved and invoked. Gate 0 and every live
Building block 3 phase remain pending and paused during the overhaul.

V1 has three sequential blocks:

1. backend preparation and processing operations;
2. reference frontend integration; and
3. TrueNAS VM deployment and trial commissioning.

An implementation block starts only when the user explicitly invokes or
approves its prompt from `BUILDING_BLOCK_PROMPTS.md`.

## Required reading

Before planning or changing the project, read completely:

- `README.md`;
- `PROJECT.md`;
- `ARCHITECTURE.md`;
- `ROADMAP.md`;
- this file; and
- the active block prompt in `BUILDING_BLOCK_PROMPTS.md`.

Read the relevant archived V0 sections when a task touches existing processors,
artifact safety, synchronization, real-data evidence, or accepted limitations.

Also inspect relevant code, tests, configuration, documentation, Git status,
and existing diffs. Existing uncommitted work belongs to the user unless proven
otherwise.

## Working method

- Work on one approved V1 building block at a time.
- State the exact block boundary before implementation.
- Implement one visible vertical slice rather than disconnected infrastructure.
- Follow the active V1 contracts and preserve inherited V0 safety/timing
  behavior.
- Prefer direct code and explicit domain names over speculative abstractions.
- Keep the implementation understandable to a first-year software-development
  student.
- Treat paths, hostnames, topics, profiles, limits, and deployment values as
  validated configuration rather than permanent constants.
- Measure expensive operations and queries rather than guessing.
- Record limitations instead of expanding the active block silently.
- Stop for direction at the stop conditions in the active block prompt.

## Approval boundaries

User approval is required before:

- starting a V1 implementation block;
- crossing into another block;
- changing the accepted V1 product, visual, architecture, data, timing, or
  deployment contract;
- introducing or installing a major runtime dependency;
- adding another worker, job kind, processor, source format, or telemetry family;
- accessing or processing real source data beyond the explicit acceptance in
  the active user-invoked prompt;
- performing a destructive filesystem, database, deployment, or Git action;
- committing completed work;
- pushing, opening a pull request, changing a remote, or publishing a release;
  or
- exposing the service outside the approved private trial boundary.

Documentation, audit, diagnosis, and planning approval is not application-code
implementation approval. A pasted block prompt is approval only for its stated
boundary and explicit real-data acceptance.

## Before editing

Briefly report:

- what was inspected;
- the active block or exact documentation/audit task;
- files expected to change;
- verification and acceptance plan;
- real-data or deployment access, if any; and
- assumptions affecting the result.

Check Git status and relevant diffs before editing. Preserve unrelated changes.

## Visual reference rules

- `archive/index.html`, `archive/styles.css`, `archive/script.js`, and
  `archive/assets/` define the V1 visual reference.
- Keep `archive/` unchanged during normal Building block 2 implementation;
  adapt or port it into `src/rosbag_analyser/web/`.
- Do not replace the design with the V0 frontend, a framework, a generic admin
  template, or personal aesthetic preferences.
- Do not show mock preview images, mock recordings, mock jobs, or simulated
  timers as real data.
- Backend-controlled values must use safe DOM construction and must not become
  HTML, selectors, URLs, or paths without validation.
- Preserve keyboard access, visible focus, reduced motion, live status, status
  text independent of color, and responsive behavior.

## Source-archive safety

Original recordings are always read-only, including development and NAS roots.

Never modify, rename, move, delete, repair, reindex, truncate, vacuum, or write
beside an original recording, including its:

- ROS bag database or MCAP file;
- `metadata.yaml`;
- camera video;
- timestamp CSV;
- directory; or
- related source file.

Never run a command that could create a journal, WAL, lock, index, repaired
metadata, cache, or sidecar in a source directory.

Open source SQLite databases explicitly read-only. Use immutable mode when safe
and compatible. A `SELECT` statement alone is not proof that a connection
cannot write auxiliary files.

Never run `ros2 bag reindex` or an equivalent repair against an original.
Report damaged data without changing it.

The recursive V1 scanner must:

- stay below configured depth, entry, and recording bounds;
- never follow symlinks;
- contain every path below the configured root;
- distinguish a malformed recording from an incomplete root traversal;
- apply missing reconciliation only after a complete successful scan; and
- create no artifact or processing job.

Move reconciliation is transactional metadata work only. It may update the
current catalog path and database ownership of existing history after a
one-to-one match, but it never moves, copies, renames, or rewrites source or
derived files. Ambiguous matches remain separate.

Real-data checks capture a safe before/after inventory of relative names, kinds,
sizes, and high-resolution modification times. Do not hash large source payloads
when the lightweight manifest is sufficient.

## Derived-data safety

- Archive and derived roots remain separate and non-overlapping.
- Every generated path is constrained to the derived root.
- Discovered names are untrusted and never become unchecked output paths.
- Incomplete work stays in a proven job-owned temporary workspace.
- Validate before publishing; use atomic rename where practical.
- Never present partial or invalid output as ready.
- Clean only paths proven to belong to the derived root and the relevant job.
- Do not delete or replace a valid artifact before its replacement is valid.
- Do not serve an artifact whose identity, manifest, file, or requested settings
  no longer match.
- A low-space condition rejects new work safely; it does not delete ready output.
- Keep generated media and telemetry out of PostgreSQL and Git.

Never commit recordings, generated videos, telemetry artifacts, credentials,
tokens, private keys, `.env` files, password files, certificates, database
dumps, private mount paths, or service state.

## Catalog and preparation discipline

- Ordinary catalog and Processing reads use PostgreSQL projections; they do not
  parse or stat source files per row.
- Current output identity comes from the successful-scan
  `preparation_targets` projection.
- A planner/configuration mismatch requires explicit rescan.
- The worker independently revalidates source identity before processing.
- **Prepare selected** is bounded and idempotent.
- Bulk preparation retains three artifact jobs; do not add a combined processor
  or duplicate recording lifecycle.
- Source unavailability creates no failed job.
- Retry recomputes current identity rather than rerunning stale work.
- Queue order displayed by the API must match worker claim order.
- Elapsed time is factual; estimates are approximate and may be unavailable or
  exceeded.
- Do not add fabricated percentage progress.

## Existing processor and timing contracts

Do not silently change:

- immutable source access;
- front-camera record-endpoint coverage with image-header cadence affinely
  mapped between those endpoints (`front-preview-v2`);
- top-down CSV Unix-timestamp timing;
- fixed H.264/yuv420p preview profile behavior;
- schema-version-2 six-axis IMU bundle;
- decimal nanoseconds, source order, duplicate-last lookup, or per-series null
  gaps;
- identity-bound range delivery;
- one browser-owned full-recording clock;
- 100-millisecond camera correction; or
- measured coverage with hide/clear outside coverage.

A visual integration request is not permission to change backend truth for
smoother playback or simpler UI code. The current front-camera rule is the
separately user-approved, versioned exception recorded in `ARCHITECTURE.md` and
`ROADMAP.md`.

## Deployment safety

- V1 deployment is private and internal. Never create public DNS, public
  firewall exposure, or port forwarding for the raw API.
- The application and PostgreSQL use private or loopback listeners behind the
  approved access proxy.
- Source storage is mounted read-only; never test it with a write probe.
- Derived storage is separate and writable only by the service account.
- Machine configuration and secrets live outside Git with least privilege.
- Migrations run once through the controlled release process, not concurrently
  from API and worker startup.
- Back up PostgreSQL before a schema-changing release and verify restore in a
  disposable target.
- Do not assume code rollback is schema-safe; follow the release's recorded
  compatibility or database-restore rule.
- Use disposable mounts/databases for outage and full-disk drills.
- Destructive deployment actions require exact target resolution and explicit
  user authority.

## Testing

Each approved block requires:

- focused unit tests for core logic;
- relevant failure and boundary coverage;
- PostgreSQL migration/repository tests where persistence changes;
- API contract tests where delivery changes;
- dependency-free browser tests where frontend behavior changes;
- visible manual acceptance;
- source-immutability evidence whenever real data is accessed; and
- deployment evidence when a VM or service is changed.

Prefer tiny synthetic archives, generated ROS messages, narrow external-tool
mocks, disposable databases, and temporary derived roots. Routine tests never
depend on the real NAS archive.

Do not weaken an accepted test to make a change pass. If a reviewed contract
changes, update the owning document and test visibly.

## Dependencies

Do not install a major dependency without the approval contained in the active
block or a separate user decision. A proposal explains:

- the exact problem;
- why existing dependencies or the standard library are insufficient;
- runtime, maintenance, and deployment impact;
- licence considerations; and
- why the active block needs it now.

Pin and document approved application dependencies. OS deployment packages and
their role still belong in the deployment inventory and runbook.

## Code quality

- Keep catalog, persistence, preparation, processing view, processors, API,
  worker, and frontend boundaries acyclic.
- Use explicit application services rather than putting workflow in routes.
- Bound list queries, request sizes, traversal, history, and estimation samples.
- Prefer cursor-based processing history where concurrent inserts matter.
- Sanitize browser errors while preserving private server diagnostics.
- Add comments only for non-obvious safety, identity, timing, or operational
  reasoning.
- Keep test fixtures narrow and intention-revealing.

## Document ownership

- `README.md`: concise V1 purpose, status, shape, safety, and navigation.
- `PROJECT.md`: V1 users, workflow, requirements, scope, and success criteria.
- `ARCHITECTURE.md`: V1 technical, data, API, timing, estimation, and deployment
  decisions.
- `ROADMAP.md`: V1 block order, boundaries, tests, and acceptance gates.
- `BUILDING_BLOCK_PROMPTS.md`: paste-ready execution instructions for each block.
- `AGENTS.md`: contribution, safety, approval, testing, and Git discipline.
- `docs/v0/`: frozen historical contracts and evidence.

Keep facts in their owner. Other documents link or summarize rather than copy
large requirements.

## Git rules

- Inspect Git status before starting and before handoff.
- Preserve unrelated user changes and untracked files.
- Do not use destructive Git commands without explicit permission.
- Do not rewrite history, force-push, delete branches, or change remotes.
- Do not fetch, pull, push, open a pull request, or publish a release unless
  requested.
- Do not commit completed work until the user reviews and approves it.
- Keep eventual commits focused on one accepted V1 block.

## Completion handoff

After implementation, report:

- approved boundary and files changed;
- migrations and API contracts;
- commands and tests run;
- manual, browser, real-data, and deployment verification actually completed;
- visible behavior and measured performance;
- source-immutability evidence;
- assumptions, limitations, deferred work, and stop conditions encountered;
- Git status and uncommitted state; and
- the exact review needed before the next block.

## Current instruction

The complete application and repository-readiness state preceding Prompt 2A is
the accepted working baseline. Preserve all accepted backend, processor,
artifact, timing, safety, moved-path, frontend, local-operation, and deployment-
readiness behavior except where the invoked Prompt 2A explicitly changes the
product contract. Establish the authorized baseline Git checkpoint before
Prompt 2A application-code work. Keep `archive/` unchanged as the frozen
overhaul reference and exclude its mock/generated payloads from Git/runtime.
Do not begin live VM mutation until Gate 0 and the exact command/rollback review
are approved; do not read authoritative source content until the real-data
annex is approved.
