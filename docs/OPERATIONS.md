# VM operations

The project owner reports the VM application running as of 2026-09-19. This
guide describes the repository's operating model. Inspect the site for its
current release and access configuration; dated observations and former
commissioning plans are in [history](history/README.md).

## Layout

| Location | Purpose |
| --- | --- |
| `/opt/rosbag-analyser/releases/<id>/` | Immutable installed releases |
| `/opt/rosbag-analyser/current` | Active release symlink |
| `/opt/rosbag-analyser/repository/` | VM Git checkout; services do not run here |
| `/opt/rosbag-analyser/staging/` | Release staging |
| `/etc/rosbag-analyser/` | Private configuration and credentials |
| `/srv/rosbag-analyser/source` | Read-only source mount |
| `/var/lib/rosbag-analyser/derived` | Writable reserved-cache mount; service writes to its `rosbag-analyser/` child |
| `/var/backups/rosbag-analyser/` | Protected database backup staging |

These are repository defaults, not private NAS locations. Source and derived
mounts remain distinct even when backed by one dataset. The writable mount
exposes only `Rosbag_Analyser_Cache`. Never test source access with a write probe.

The `rosbag-analyser` account runs API and worker. Releases/configuration are
root-owned. Keep `application.env` and `migration.env` at
`root:rosbag-analyser 0640`; `backup.env`, pgpass and CIFS credentials are
root-owned `0600`. Use separate runtime, migration-owner and backup database
roles. Secrets, real endpoints and access lists stay outside Git.

[Deployment assets](../deploy/README.md) index configuration and package inputs.
Keep a private site record of current release/schema, mounts, access route,
backup/restore procedure, recovery access and responsible operator.

## Routine checks

From this PC, use the existing private SSH settings:

```bash
./vm status
./vm logs
./vm deploy --push
```

`status` saves release, service and health facts; `logs` returns the last 200
API/worker journal lines with common secrets and paths redacted. Reports land
in a new private `.vm-reports/<timestamp>-<action>/` directory here. Each includes
`report.json`, `stdout.txt`, `stderr.txt`, SSH errors and checksums. Reports are
ignored by Git and remain available when a command fails. Review before sharing.

`status` runs without sudo and prints a short summary. Missing or denied checks
produce an incomplete report and a nonzero exit; a complete report can still
show failed services or unhealthy HTTP responses. `logs`, diagnostics and
deployment use sudo. In a terminal, SSH prompts for the VM sudo password when
required; the password is never stored in reports. Without a terminal, these
commands require existing non-interactive sudo access and explain when it is
missing. Interactive commands stage their input and captured output in a private
VM `/tmp/rosbag-vm-*` directory, removed after collection. A broken connection
can leave that directory behind; its location is reported if collection fails.

For direct VM inspection:

```bash
systemctl status rosbag-analyser-api.service rosbag-analyser-worker.service --no-pager
systemctl status rosbag-analyser-preflight.service rosbag-analyser.target --no-pager
curl --fail --silent http://127.0.0.1:8000/health/live
curl --fail --silent http://127.0.0.1:8000/health/ready
findmnt --mountpoint /srv/rosbag-analyser/source --output TARGET,SOURCE,FSTYPE,OPTIONS
findmnt --mountpoint /var/lib/rosbag-analyser/derived --output TARGET,SOURCE,FSTYPE,OPTIONS,SIZE,AVAIL
journalctl -u rosbag-analyser-api.service -u rosbag-analyser-worker.service --since today --no-pager
```

Raw output can contain private values. For shareable evidence, run
`/opt/rosbag-analyser/current/deploy/scripts/collect-support-bundle` with a new
protected output directory, then review the result before sharing.

Readiness distinguishes capabilities: source loss or low derived capacity may
disable new work while saved state remains available. Inspect API/worker units
as well as their grouping target.

## Routine deployment

```text
reviewed/tested commit → ./vm deploy --push → immutable release → health/smoke
```

Workstation settings live in mode-0600/0400
`~/.config/rosbag-analyser/vm-deploy.env`, based on the example in `deploy/`.
`--push` checks local eligibility, pushes the existing commit, then invokes
`./deploy-vm`. It never commits files automatically. Omit `--push` if already
pushed. `./deploy-vm --check` validates local eligibility without contacting the
VM. Application/release changes must be committed; local docs, tests and
diagnostic helpers do not block deployment and are not included.

The committed deployment script is sent over SSH, so updating the deployment
tool itself does not require manually copying it onto the VM first. Application
code still comes from the exact pushed revision in the dedicated VM checkout.

The VM fast-forwards its dedicated checkout and builds using the active checked
wheelhouse. Frontend changes restart API only; other application changes drain
the worker and restart both. Documentation/tests alone update the checkout
without activating a release. Standalone topic-audit tools and the Git deployer
are also allowed by the routine classifier.

Other deployment scripts, dependencies, migrations, service/proxy/firewall
and configuration templates use the planned procedure below. The classifier in
`deploy/scripts/deploy-from-git` is authoritative. It never scans or prepares.
If health/smoke fails after activation, inspect the active pointer and services;
the routine deployer does not automatically roll back.

## Run a diagnostic and get the result back

```bash
./vm topics --recording 'folder/recording'
./vm front-headers --recording 'folder/recording' --max-messages 100000
./vm run tools/diagnostics/runtime_info.py
./vm run --recording 'folder/recording' tools/diagnostics/my_check.py -- argument
```

Recording paths are relative to the configured archive root; repeat
`--recording` for several. Root and topic settings come from the VM. Put wrapper
options before the custom script path; arguments after it are passed literally
to the script. `--timeout` changes the default five-minute limit (up to one hour);
`--output` selects a new local report directory. Source inventories have explicit
`--max-depth` and `--max-entries` bounds.

`run` sends the current local Python file, including uncommitted edits. It needs
no push, install, application release or restart. The VM stages it temporarily
and uses the active release's Python environment plus ROS Humble. Print results
to stdout (JSON/CSV/text); they return in `stdout.txt`. Arbitrary generated files
and sibling Python modules are not transferred. A script's installed application
imports reflect the running release, not uncommitted local backend edits.

Diagnostics run as `rosbag-analyser` in a transient systemd sandbox: filesystem
writes outside its temporary work area are blocked, network/database access and
private service configuration are hidden, and runtime/memory/output are bounded.
Without `--recording`, the source root is hidden too. With a selection, scripts
must limit reads to it; the wrapper compares lightweight inventories before and
after, including script failures. It reports incomplete evidence on hard kills
or transport failures rather than claiming source safety was verified. Original
source mounts must be read-only. No application service is restarted.

Scripts receive `ROS_BAG_ANALYSER_ARCHIVE_ROOT`, configured front/IMU topic
variables, and `VM_DIAGNOSTIC_RECORDINGS` (a JSON list of relative directories).
The SSH operator needs sudo access for the receiver and systemd-run; no sudoers
change is needed for normal password authentication in a terminal. Connection
failures show their cause and are saved in `ssh-stderr.txt`; check VM power,
network/VPN and the private SSH settings before retrying. Interactive sudo
authentication errors appear directly in the terminal.

## Planned releases and new installations

Stage candidates beside the running release. Record target, interruption,
backup and rollback before switching. Use the platform in
`deploy/release-contract.json` to build:

```bash
deploy/scripts/build-wheelhouse /protected/staging/wheelhouse-RELEASE BUILDER
deploy/scripts/build-release RELEASE BUILDER \
  /protected/staging/wheelhouse-RELEASE /protected/staging/release-RELEASE
```

The builder requires clean committed source. Verify archive and installer
checksums, then run the output directory's `install-release` with release ID,
absolute archive path and expected SHA-256. Installation validates contents and
dependencies and refuses to replace an existing release.

For a new VM, provision runtime packages, service identities, separate mounts,
local database roles, private configuration and the access proxy. Render the
`deploy/` templates for that site; placeholders are intentionally invalid.
Use `validate-site`, `validate-firewall`, `validate-proxy`, `nginx -t` and
systemd validation before applying configuration. Source stays read-only;
API and database remain local behind the access boundary.

For an upgrade:

1. Record active release/schema and rollback compatibility; stage and validate
   the candidate and available capacity.
2. Close engineer writes at the site proxy and run the active release's
   `deploy/scripts/drain-worker`. Resolve paused work using resume/cancel first;
   drain refuses paused work.
3. Back up PostgreSQL, retaining configuration and derived recovery information.
   Verify the dump and its protected off-VM copy.
4. Stop worker and API. Apply candidate migrations once through
   `rosbag-analyser-migrate@RELEASE.service`; startup never migrates.
5. Use `deploy/scripts/activate-release RELEASE`, rerun preflight, start API and
   worker, and run `deploy/scripts/smoke-check`.
6. Check saved catalog, queue, representative output and media ranges before
   reopening access. Retain the previous release until the update is accepted.

Enable the application target and verify guest boot persistence when setting
up or changing boot behavior. Verify TrueNAS VM-autostart separately; an
application update does not require a NAS-host reboot.

## Backup and recovery

With private backup environment and `PGPASSFILE` configured, run
`deploy/scripts/backup-database BACKUP_DIRECTORY RELEASE_ID`. Keep the verified
custom dump in an independent protected location. Periodically test
`restore-disposable-database DUMP_FILE rosbag_analyser_restore_CASE` against a
new disposable target. A dump listing alone is not a restore test.

Restored metadata must agree with derived files: restore a coherent snapshot
or identify absent artifacts for deliberate regeneration. Never mark missing
files ready. Keep backup contents and secrets out of support reports.

For rollback, close writes and stop services before switching releases.
Code-only rollback requires compatibility with the current schema. Otherwise
restore the verified database into a new target with its derived-state policy,
update configuration, preflight and smoke-test, then reopen access. Do not
invent down migrations; schema 0008 is not automatically safe for older code.

## Source checks and incidents

Rescan is explicit through the operator interface/API. It refreshes catalog
and output identities without creating jobs. Retry and queue controls belong
in the application, not hand-edited database rows.

Bound real-source diagnostics to an identified root, selected recordings and
intended work. Capture lightweight before/after inventories using
`rosbag-analyser-source-manifest`, outside source and Git. Compare relative
names, kinds, sizes and high-resolution mtimes; do not hash large payloads.
Diagnostic tools are listed in `deploy/README.md`; inspect their CLI bounds.

| Symptom | Response |
| --- | --- |
| Worker offline/interrupted | Inspect logs and lock ownership, recover one worker and explicitly retry |
| Wrong/missing/writable source mount | Stop source-dependent work and restore the configured read-only mount |
| Low derived space | Add capacity or plan retention; new work is rejected without deleting ready output |
| Database/derived storage loss | Restore the dependency, preserve state and avoid restart loops |
| Failed deployment | Inspect revision/schema and logs, then use the recorded rollback |

Assign backup checks, capacity, access/certificate maintenance and platform
updates to an operator. Use disposable targets for outage/full-disk drills.
Resolve exact targets before destructive recovery or storage changes.
