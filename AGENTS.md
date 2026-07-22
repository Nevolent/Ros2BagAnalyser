# AGENTS.md

## Purpose

This file contains standing instructions for Codex and other automated
contributors working in this repository.

ROS 2 Bag Analyser is a fresh implementation. The previous local codebase was
deliberately discarded. Do not reconstruct or depend on old prototypes unless
the user explicitly requests a specific recovery.

Building blocks 1 and 2 were completed and user-accepted on 2026-07-21.
Building block 3 implementation was approved on 2026-07-21 for the exact
top-down-camera and dual-video-synchronization boundary in `ROADMAP.md`, and
its implementation and automated verification were completed on 2026-07-22.

## Required reading

Before planning or changing the project, read:

- `README.md`;
- `PROJECT.md`;
- `ARCHITECTURE.md`;
- `ROADMAP.md`;
- this file.

Also inspect relevant code, tests, configuration, documentation, Git status,
and existing diffs. `ROADMAP.md` is the authority for whether a building block
has started or finished.

## Working method

- Work on one approved, coherent subsystem at a time.
- Prefer a visible vertical slice over isolated infrastructure.
- State the subsystem boundary before implementation.
- Do not begin work assigned to a later roadmap block.
- Follow the accepted product and architecture contracts.
- Keep the implementation understandable to a first-year software-development
  student.
- Prefer direct code over speculative abstractions.
- Treat development paths, filenames, and topic names as configuration
  examples, not permanent constants.
- Stop for direction if work needs a material architecture decision, safety
  exception, major dependency, or scope expansion.

## Approval boundaries

User approval is required before:

- starting a roadmap building block;
- crossing into another building block;
- changing an accepted product or architecture contract;
- introducing or installing a major runtime dependency;
- changing the persistent storage or processing-job model;
- processing original data outside the approved subsystem;
- taking a destructive filesystem or Git action;
- committing completed work;
- pushing or otherwise changing a remote repository.

An audit, review, diagnosis, plan, or documentation change is not permission to
implement application code.

## Before editing

Briefly report:

- what was inspected;
- the approved roadmap block, or the exact documentation/audit task when no
  implementation block is active;
- files expected to change;
- the verification plan;
- assumptions affecting the result.

Check Git status and relevant diffs first. Preserve unrelated user changes.

## Source-archive safety

The original development archive is always read-only:

```text
Windows: D:\Rosbags
WSL:     /mnt/d/Rosbags
```

These are development examples, not production configuration.

Never modify, rename, move, delete, repair, reindex, truncate, vacuum, or write
beside an original recording, including its:

- ROS bag database or MCAP file;
- `metadata.yaml`;
- camera video;
- timestamp CSV;
- recording directory or related source file.

Never run a command that could create a journal, WAL, lock, index, repaired
metadata, cache, or sidecar in an original recording directory.

Open original SQLite databases explicitly read-only. Use immutable mode when it
is safe and compatible. A `SELECT` statement alone is not proof that a
connection cannot create auxiliary files.

Never run `ros2 bag reindex` or an equivalent repair operation on an original.
Report damaged data without changing it.

Generated output must go to the configured derived-data root, never into
`/mnt/d/Rosbags` or beside a source.

Real-archive checks must compare a safe before/after inventory. Do not hash more
than 100 GiB for routine evidence when names, sizes, and modification times are
sufficient.

## Derived-data safety

- Keep archive and derived roots separate and reject overlapping roots.
- Constrain every generated path to the derived root.
- Treat discovered names as untrusted path components.
- Prevent path traversal and output collisions.
- Write incomplete work to a temporary workspace under the derived root.
- Validate output before publishing it, using an atomic rename where practical.
- Never present partial or invalid output as ready.
- Clean up only paths proven to belong to the derived root.
- Do not replace or delete a valid artifact before its replacement is valid.
- Never serve an artifact whose input identity or output settings no longer
  match the current request.
- Keep large generated payloads in the approved artifact store, not application
  metadata storage.

Never commit:

- `*.db3` or `*.mcap` files;
- generated videos or extracted frames;
- large telemetry artifacts or test data;
- credentials, tokens, private keys, `.env` files, or environment secrets;
- sensitive machine-specific storage locations.

## Implementation discipline

Follow `ARCHITECTURE.md` for accepted technical boundaries and `ROADMAP.md` for
the exact scope of the active building block. In particular:

- scanning must not generate previews or telemetry;
- expensive ROS, video, or telemetry processing must not run in route code;
- ROS readers and processors must remain usable without FastAPI or the browser;
- the frontend must never read source files directly;
- later features must not be introduced for convenience.

Do not silently change the accepted time model:

- ROS record timestamps drive ROS stream alignment;
- CSV Unix timestamps drive top-down timing;
- synchronized streams report their time provenance and coverage;
- the UI must not freeze a boundary frame in a way that implies false coverage.

## Testing

Each approved subsystem must have:

- focused automated tests for its core logic;
- relevant failure coverage;
- a visible manual acceptance procedure;
- source-immutability evidence when real data is used.

Prefer tiny synthetic fixtures, generated messages, narrow external-tool mocks,
and temporary output directories. Routine tests should not require ROS or the
full archive where a smaller fixture can prove the behavior.

Real-archive checks are opt-in, strictly read-only, identifiable by recording
and topic, and not required in generic CI. Exact minimum tests and real-data
acceptance cases belong to the active roadmap block.

Do not weaken an accepted test merely to make a change pass. If an accepted
contract changes, explain and update the test visibly.

## Dependencies

Do not install dependencies without approval. A dependency proposal must
explain:

- the problem it solves;
- why existing dependencies or standard-library code are insufficient;
- maintenance and deployment impact;
- relevant licence considerations;
- why the active V0 block needs it now.

Pin and document approved dependencies through the selected package-management
approach.

## Code quality

- Use explicit domain names and focused functions or classes.
- Avoid circular dependencies between catalog, persistence, processing, API,
  and UI code.
- Centralize and validate configuration.
- Keep local paths out of core logic and browser responses.
- Sanitize browser errors while retaining useful server diagnostics.
- Add comments only when the reasoning is not apparent from the code.
- Measure expensive operations rather than guessing.
- Document non-obvious safety, identity, and timing decisions close to code.

## Document ownership

- `README.md`: brief purpose, maturity, architecture summary, and links.
- `PROJECT.md`: product goals, source-data facts, V0 scope, and success criteria.
- `ARCHITECTURE.md`: accepted V0 technical boundaries and decisions.
- `ROADMAP.md`: build order, block scope, visible acceptance, and minimum tests.
- `AGENTS.md`: contribution process, safety, approvals, Git, and coding
  discipline.

Keep each fact in its owning document. Other files should link or summarize
rather than restating detailed requirements.

## Git rules

- Inspect `git status` before starting and before reporting completion.
- Preserve unrelated user changes.
- Do not use destructive Git commands without explicit permission.
- Do not rewrite history, force-push, or delete branches without permission.
- Do not add or change remotes, fetch, pull, push, or open a pull request unless
  requested.
- Do not commit completed work until the user reviews and approves it.
- Keep each eventual commit focused on one accepted subsystem.

## Completion handoff

After implementation, report:

- the approved boundary and files changed;
- commands and automated tests run;
- manual and real-data verification;
- visible behavior and performance observations;
- source-immutability evidence;
- assumptions, limitations, and deferred work;
- Git status and uncommitted state.

User review is required before committing or beginning the next block.

## Current instruction

During Building block 3:

- Building blocks 1 and 2 are complete and accepted;
- Building block 3 is implemented only for the top-down AVI/CSV processor and
  dual-video synchronization boundary in `ROADMAP.md`; its opt-in acceptance
  remains pending;
- preserve the accepted front-preview behavior and four-table, one-worker
  processing model;
- do not add telemetry, IMU processing, or later-roadmap features;
- do not access the real archive without explicit opt-in acceptance approval;
- do not begin Building block 4 without separate user review and approval.
