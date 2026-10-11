# Operations

## Layout and access

| Path | Purpose |
| --- | --- |
| `/opt/rosbag-analyser/releases/<id>/` | Immutable releases |
| `/opt/rosbag-analyser/current` | Active release symlink |
| `/opt/rosbag-analyser/repository/` | Deployment checkout; services do not run here |
| `/opt/rosbag-analyser/staging/` | Release and model-download staging |
| `/opt/rosbag-analyser/models/<runtime-id>/` | Verified offline CPU model and native runtime |
| `/etc/rosbag-analyser/` | Private configuration and credentials |
| `/srv/rosbag-analyser/source` | Read-only source mount |
| `/var/lib/rosbag-analyser/derived` | Writable cache mount; application uses its `rosbag-analyser/` child |
| `/var/backups/rosbag-analyser/` | Protected database backup staging |

Source and derived mounts stay distinct, even on one NAS dataset. The writable
mount exposes only `Rosbag_Analyser_Cache`. Never test source access by writing.

The `rosbag-analyser` account runs API and worker; releases and configuration
are root-owned. Set `application.env` and `migration.env` to
`root:rosbag-analyser 0640`; backup configuration, pgpass and CIFS credentials
are root-owned `0600`. Use separate runtime, migration-owner and backup database
roles. Keep endpoints, credentials, access lists and the site recovery record
outside Git. Templates and tool descriptions are in [deploy/](../deploy/README.md).

## Status and logs

Workstation connection settings belong in mode-0600/0400
`~/.config/rosbag-analyser/vm-deploy.env`; start from the example in `deploy/`.

```bash
./vm status
./vm logs
```

Each command writes private reports to a new ignored
`.vm-reports/<timestamp>-<action>/` directory, including JSON, stdout, stderr,
SSH errors and checksums. Logs include separate snapshots of the last 200 lines from each API/worker journal
with common secrets and paths redacted. Review reports before sharing.

`status` needs no sudo. Missing checks produce an incomplete report and nonzero
exit; a complete report may still show unhealthy services. Logs, diagnostics and
deployment use sudo. Interactive SSH can prompt for the password, which is not
stored; unattended commands need existing non-interactive sudo access.
Temporary VM `/tmp/rosbag-vm-*` directories are removed after collection; a
broken connection may leave one behind, with its location reported.

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

Raw output may contain private values. `deploy/scripts/collect-support-bundle`
creates a bundle in a new protected directory; review it before sharing.
Readiness reports capabilities: source loss or low derived space can disable
new work while saved state remains readable. Check individual units as well as
the grouping target. Service health does not establish job success; use the
Processing failure diagnostics and the worker journal for preparation failures.

## Deploy a commit

For an existing configured VM, run this from the workstation project root in WSL:

```bash
./vm deploy
```

The branch must be committed and pushed, and the VM must be reachable using the
private SSH settings described above. Deployment needs sudo access, healthy
database/mount configuration and no paused jobs. A new VM needs the installation
procedure below.

`./deploy-vm --check` checks only local settings, branch and uncommitted runtime
files; it does not connect to the VM or validate the upgrade from its active release.
For future committed changes, `./vm deploy --push` pushes the branch and deploys
it in one command.

Application and release changes must be committed. Local documentation, tests
and diagnostic helpers do not block deployment and are not included.
The command never commits automatically. It sends the deployment script over
SSH, then fast-forwards the dedicated VM checkout and validates the exact pushed
revision. Documentation/test-only changes update that checkout without
activating a release.

Pending migrations, model setup and health checks are included in this command.
The release includes the committed browser assets; an already configured VM needs
no separate migration, frontend build or model-setup command.

The deployer stages an immutable release before interrupting services. It also
provisions/checks the candidate's pinned CPU model and runs synthetic inference
as the service account before closing writes. Download, build or inference
failure leaves the active release running. The Linux x86_64 builder needs
`python3-pip`, `python3.10-venv`, `build-essential` and `cmake`. On the configured
VM, provision missing OS packages before deployment:

```bash
sudo apt-get update
sudo apt-get install --no-install-recommends python3-pip python3.10-venv build-essential cmake
```

First setup downloads about 2.65 GB of weights plus llama.cpp
source and needs at least 8 GiB free staging space. Subsequent releases reuse
verified runtime assets. The runtime uses CPU feature dispatch, including a
baseline backend for guests that expose no AVX. It requires no compute GPU.

`ROS_BAG_ANALYSER_DESCRIPTION_RUNTIME_ROOT` defaults to the pinned directory
under `/opt/rosbag-analyser/models/`; overrides must be direct children of that
root. `ROS_BAG_ANALYSER_DESCRIPTION_THREADS` defaults to four. Native binaries
and weights are root-owned and readable/executable by the service account;
recording processing never downloads them. Do not place model assets on the
source or derived mount. Model/build cache cleanup is an explicit operator action.
The synthetic smoke check reports elapsed time on the guest; it is not a promise
of real-recording latency or description accuracy.
Frontend-only changes restart API only. Other application changes close writes
and let active worker work finish; queued work remains saved. Dependency changes
build a checked wheelhouse on the existing platform. OS/ROS/Python or service,
proxy, firewall and private configuration changes use the site-upgrade procedure.
The planner also accepts the reviewed installer change that publishes only
`wheelhouse/SHA256SUMS` as `0644` after root ownership and before release publication;
any accompanying installer change still requires a site upgrade.

Migrations must be appended consecutively; existing migrations cannot change.
Before migrating, the deployer stops API and worker, creates a protected dump,
restores it into a fresh disposable database, and checks the previous release's
schema. It copies and verifies the dump under a new local
`.vm-reports/<run>-deploy/` directory and waits for that acknowledgement before
running the migration service. PostgreSQL inspection, backup and disposable
restore use the `postgres` OS account with peer authentication. Migration role
and unit checks happen before interruption. Transfers are bounded to 10 GiB and
ten minutes; each attempt records its exit status in `result.json`. Failed backup
transport commands save bounded SSH diagnostics in private `backup-transport.jsonl`.
Status polling retries up to three consecutive SSH failures or timeouts; invalid
backup markers and failed checksum checks still stop deployment.

Native WSL/Linux OpenSSH deployments establish and check a private shared SSH
connection before starting remote deployment. Staging, the sudo session, backup
polling, transfer and acknowledgement reuse it, avoiding repeated handshakes
during model setup. The connection closes after report collection and has a
60-second idle expiry if the local helper is killed. Windows `ssh.exe` retains
separate connections; repeated banner-exchange timeouts during deployment call
for native WSL OpenSSH with its own working key and known-host configuration.

The root-owned `/run/rosbag-analyser-maintenance` gate blocks mutations and new
worker claims until candidate preflight, API health/smoke and service startup
pass. API access is unavailable while the old worker drains and backup/migration
runs; reads and media return when the candidate API starts. Resolve paused jobs
through the resume/cancel API before deployment. Drain waits up to one hour
without force-killing processors. An exclusive VM lock serializes deployments.
Deployment never scans or prepares recordings.

Success requires the expected API release and online worker. Frontend updates
and recovery also verify the expected API release. Failure reopens a compatible
previous release automatically. If that release cannot validate the changed
schema, services remain stopped with the gate, dump and recovery configuration
under `/var/backups/rosbag-analyser/deploy-<release>-<run>/`. The error identifies
the directory. An incomplete maintenance gate blocks another deployment; use
the recovery procedure below.

## Diagnostics

```bash
./vm topics --recording 'folder/recording'
./vm front-headers --recording 'folder/recording' --max-messages 100000
./vm run tools/diagnostics/runtime_info.py
./vm run --recording 'folder/recording' tools/diagnostics/my_check.py -- argument
```

Recording paths are relative to the configured root; repeat `--recording` as
needed. Put wrapper options before the script; trailing arguments pass through
literally. `--timeout` sets the five-minute default, up to one hour.
`--output` selects a new local report directory. Inventories have explicit
`--max-depth` and `--max-entries` limits.

`run` transfers the current local Python file, including uncommitted edits, into
a temporary VM directory. It uses the active release's environment and Humble;
no push, installation or restart is needed. Print JSON/CSV/text to stdout.
Generated files and sibling modules are not transferred; application imports
come from the active release.

Diagnostics run as `rosbag-analyser` in a transient systemd sandbox with bounded
runtime, memory and output. Writes outside its temporary directory, network,
database and private service settings are blocked. Source is hidden unless
recordings are selected. Scripts must stay within that selection. The wrapper
compares lightweight before/after inventories even on script failure; hard
kills or transport failure produce incomplete evidence. Source mounts must be
read-only.

Scripts receive `ROS_BAG_ANALYSER_ARCHIVE_ROOT`, configured front/IMU topics and
`VM_DIAGNOSTIC_RECORDINGS` (JSON relative paths). The SSH operator needs sudo
for the receiver and systemd-run. Connection errors are saved in
`ssh-stderr.txt`; check VM power, network/VPN and private SSH settings.

## New installations and site upgrades

Record the target, interruption, backup and rollback before changing a site.
Stage candidates beside the active release using the platform in
`deploy/release-contract.json`:

```bash
deploy/scripts/build-wheelhouse /protected/staging/wheelhouse-RELEASE BUILDER
deploy/scripts/build-release RELEASE BUILDER \
  /protected/staging/wheelhouse-RELEASE /protected/staging/release-RELEASE
```

Build from clean committed source. Verify archive and installer checksums, then
run the output's `install-release` with release ID, absolute archive path and
expected SHA-256. Installation validates dependencies and refuses replacement
of an existing release.

For a new VM, provision packages, service identities, separate mounts, local
database roles, private configuration and the access proxy. Render the
intentionally invalid template placeholders. Run `validate-site`,
`validate-firewall`, `validate-proxy`, `nginx -t` and systemd validation before
applying settings. Source stays read-only; API and database stay local behind
the access boundary.

For a new installation, provision and smoke-test the model before activation
using the candidate's installed environment:

```bash
sudo /opt/rosbag-analyser/releases/RELEASE/venv/bin/python \
  /opt/rosbag-analyser/releases/RELEASE/deploy/scripts/prepare-model-runtime \
  /opt/rosbag-analyser/releases/RELEASE
```

Candidate preflight requires a valid model runtime. For a site upgrade or manual recovery:

1. Record the active release/schema and rollback compatibility. Stage and validate
   the candidate and capacity.
2. Close writes at the proxy. Resolve paused work through the resume/cancel API,
   then run the active release's `deploy/scripts/drain-worker`.
3. Back up PostgreSQL, configuration and derived recovery information. Verify the
   dump and a protected off-VM copy.
4. Stop worker and API. Apply migrations once with
   `rosbag-analyser-migrate@RELEASE.service`; startup never migrates.
5. Run `deploy/scripts/activate-release RELEASE`, preflight, service startup and
   `deploy/scripts/smoke-check`.
6. Check saved catalog, queue, representative output and media ranges before
   reopening access. Retain the previous release until the update is accepted.

Verify application target enablement and guest boot persistence when changing
boot setup. TrueNAS VM autostart is a separate setting; application updates do
not require a NAS-host reboot.

## Backup and recovery

If deployment aborted with the previous release still selected, use
`./vm recover`. It requires a free deployment lock, a stopped migration,
compatible schema and no running or paused jobs. It starts both stopped
services, or validates both already active services without restarting them;
mixed or transitional service states require inspection. Maintenance clears
only after the expected API release is ready and the worker is online.
It does not restore data or switch releases. A schema mismatch needs the
rollback procedure below. After successful recovery, retry `./vm deploy`.

If migrations completed and the recorded candidate is already selected, inspect
the preflight journal before retrying startup:

```bash
journalctl -u rosbag-analyser-preflight.service -n 60 --no-pager
./vm recover --candidate && ./vm status
```

Candidate recovery checks the installed release identity, compatible schema,
stopped migration and absence of running or paused jobs. It repairs service read
access to root-owned `wheelhouse/SHA256SUMS` only when its content matches the
release manifest; installation publishes this non-secret metadata as `0644`.
It then runs preflight, starts stopped services and verifies the expected API,
online worker and smoke checks before clearing maintenance. Failures retain the
gate and recovery files. This command never reruns migrations, restores the
database or changes release pointers; the default `./vm recover` still requires
the previous release to be selected.

With private backup settings and `PGPASSFILE`, run
`deploy/scripts/backup-database BACKUP_DIRECTORY RELEASE_ID`. Keep the verified
custom dump in an independent protected location. Periodically test
`restore-disposable-database DUMP_FILE rosbag_analyser_restore_CASE` against a
new disposable target. Listing a dump is not a restore test.

Restored metadata must match derived files: restore a coherent snapshot or
identify absent artifacts for deliberate regeneration. Never mark missing files
ready. Keep dumps and credentials out of support reports.

For rollback, close writes and stop services first. Code-only rollback requires
schema compatibility. Otherwise restore the verified database into a new target,
resolve derived-state consistency, update private configuration, preflight and
smoke-test before reopening. Do not invent reverse migrations or assume older
code can read a newer schema.

## Source checks and incidents

Rescan explicitly through the operator interface/API. It refreshes saved catalog
and identities, retries thumbnails and completes available outputs for previously
prepared recordings, reusing validated compatible artifacts and active jobs.
Use Prepare Selected for a recording's first full preparation or a selective retry;
use queue controls rather than database edits. Code updates and deployment alone do
not retry saved failures.

Bound source checks to an identified root, selected recordings and intended work.
Use `rosbag-analyser-source-manifest` for lightweight before/after inventories,
outside source and Git. Compare names, kinds, sizes and high-resolution mtimes;
do not hash large payloads.

| Symptom | Response |
| --- | --- |
| Worker offline/interrupted | Inspect logs and lock ownership, restore one worker, retry explicitly |
| Missing/writable source mount | Stop source-dependent work; restore the configured read-only mount |
| Low derived space | Add capacity or plan retention; ready output is not deleted automatically |
| Database/derived storage loss | Restore the dependency and preserve saved state |
| Failed deployment | Inspect revision, schema and logs; use the recorded recovery procedure |

Assign backup checks, capacity, access/certificate maintenance and platform
updates to an operator. Use disposable targets for outage and full-disk drills.
