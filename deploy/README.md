# V1 NAS trial deployment assets

This directory contains repository-owned templates and tooling for V1 Building
block 3. It does not contain an active site configuration and none of these
files changes TrueNAS.

Repository Phase 1 was implemented and locally verified on 2026-08-16. Gate 0,
clean immutable release creation, live VM installation, authoritative-source
access, guest reboot, and trial admission remain incomplete.

Prompt 2A updates the repository candidate through additive schema migration
0007 and the approved processing-control routes. The Nginx template applies the
existing mutation rate limit to pause/resume/cancel, bounded bulk
cancel/reorder/retry, and preparation. `drain-worker` fails closed if current
work is paused or pause-requested; the operator must explicitly resume or
cancel that exact job before a planned upgrade. These repository changes are
not evidence that any live guest was migrated.

The deployment is intentionally split into four gates:

1. complete `GATE0_HANDOFF.example.md` and the private site inventory;
2. build a checksummed wheelhouse and a clean-source immutable release;
3. render and review the exact guest files, commands, interruption, backup, and
   rollback before installing anything; and
4. complete `REAL_DATA_ANNEX.example.md` before the first content read from the
   authoritative source.

The default guest layout is:

```text
/opt/rosbag-analyser/releases/<release-id>/
/opt/rosbag-analyser/current -> releases/<release-id>
/opt/rosbag-analyser/repository/  # dedicated clean Git checkout; never run services here
/etc/rosbag-analyser/application.env
/etc/rosbag-analyser/runtime.pgpass
/etc/rosbag-analyser/migration.pgpass
/srv/rosbag-analyser/source
/var/lib/rosbag-analyser/derived
```

`environment.example` contains placeholders only. Active configuration,
credentials, certificates, htpasswd files, mount identities, firewall
allowlists, database dumps, source manifests, and support bundles stay outside
Git and are root-owned.

`apt-packages.in`, the runtime/build requirement inputs, `release-contract.json`,
and the wheelhouse/release scripts bind the reviewed runtime and application
identity. `systemd/`, `nginx/`, and `firewall/` are templates, not files to copy
without rendering. `migration-environment.example` and
`backup-environment.example` keep privileged database paths distinct from the
runtime role. `GATE0_HANDOFF.example.md` and `REAL_DATA_ANNEX.example.md` remain
deliberately incomplete until their private owner records are approved.

Repository scripts fail closed and use explicit targets. They do not edit
TrueNAS, create public listeners, rescan on startup, or automatically delete a
release, database, backup, derived artifact, or source file. See
`docs/NAS_TRIAL_RUNBOOK.md` for the reviewed sequence and rollback rules.

The supported TrueNAS layout may keep an ordinary
`Rosbag_Analyser_Cache/` folder inside the existing source dataset. The VM
keeps the existing read-only source mount and mounts the cache subdirectory as
the CIFS UNC `//server/TO_Rosbag_databank/Rosbag_Analyser_Cache` for writable derived output. Production
source walkers reserve and exclude the folder before discovery, limits,
manifests, sizes, and identities.

## Read-only front-camera diagnostics

`scripts/analyze-front-header-timestamps` investigates selected failed
front-camera recordings without queuing work or generating media. It accepts
only an absolute, non-symlink archive root and explicit archive-relative
recording directories; it never traverses the archive to discover recordings.
It reads the declared ROS SQLite file by an immutable descriptor path with
SQLite query-only mode and prints a JSON report to standard output. Redirect
that output only to the protected evidence location outside the source mount.

The tool reports image encoding counts and the first encoding that the current
preview contract cannot process, as well as the first invalid image header
(message position/ID, ROS record timestamp, `sec`, `nanosec`, and reason), all
invalid-header counts, and strict-order violations. It is diagnostic only: it
does not change the preview timing policy or make an invalid recording
processable. It reads source payloads, so it may run only under an approved
real-data annex with the required before/after source-inventory evidence.

## Read-only selected-recording topic audit

`scripts/audit-recording-topics` investigates front/IMU unavailability without
queuing work or decoding messages. It accepts an absolute non-symlink archive
root, the exact configured front and IMU topic names, and either explicit
archive-relative recording paths or `--all`. The latter uses the same bounded,
non-symlink recording discovery limits as the catalog. For each recording it
compares the bounded `metadata.yaml` topic facts with the SQLite `topics` table,
opened through a read-only file descriptor using SQLite immutable and query-only
mode. Its JSON report identifies exact configured matches, type/serialization
mismatches, and alternative standard Image or Imu topic names.

The audit writes JSON Lines to standard output: one report per recording and a
final summary record. It does not count or read message payload rows; metadata
remains the source of reported message counts. Redirect output only to an
approved evidence location outside the source mount. Because the tool reads
authoritative source content, its exact command, evidence path, and before/after
source inventory remain subject to the real-data annex approval.

## Routine Git deployments

After the initial reviewed installation, routine source changes can use the
repository-owned `./deploy-vm` command from WSL. It verifies that the current
branch is clean and exactly matches `origin`, then asks the VM to fast-forward
its dedicated checkout and build a new immutable release from that exact SHA.
It never copies source files to the VM. Configure its private WSL settings from
`vm-deploy-environment.example`; do not commit that settings file.

The VM checkout is intentionally separate from `/opt/rosbag-analyser/current`.
System services continue to execute only immutable releases. The command drains
the worker before a worker-code update, selects API-only restart for served
frontend files, restarts both services for other application changes, and runs
local health plus smoke checks. It refuses migrations, dependency changes, and
systemd/Nginx/firewall/template changes because those retain the controlled
backup, migration, rendered-file, and rollback procedure in the runbook.
