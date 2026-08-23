# NAS trial operator runbook

## Status and authority

This runbook implements the repository side of V1 Building block 3. It is not
evidence that a VM was installed or that the trial is open. The live sequence
starts only after the private Gate 0 record based on
[`deploy/GATE0_HANDOFF.example.md`](../deploy/GATE0_HANDOFF.example.md) is
complete and the project owner has reviewed the exact rendered files, commands,
interruption, backup, and rollback.

The repository never administers TrueNAS. Dataset, zvol, share, ACL, snapshot,
VM, bridge, host firewall, appliance update, certificate, and recovery-console
changes belong to the infrastructure administrator. Never substitute an
unreviewed device, export, address, path, database, or backup target in the
commands below.

Before the first source content read, complete and approve
[`deploy/REAL_DATA_ANNEX.example.md`](../deploy/REAL_DATA_ANNEX.example.md).
Mount metadata may be inspected earlier; directory entries may not.

## Stop conditions

Stop without improvising if Gate 0 is incomplete; the target is ambiguous; the
source export or client mount is writable, broad, absent, or wrong; the derived
device is uncertain; IPv4 or IPv6 exposure is unproved; backup/restore cannot be
proved; a migration is rollback-unsafe; the accepted Ubuntu 22.04/ROS Humble
runtime is unavailable; or source metadata changes during acceptance.

Formatting a filesystem, dropping a database, changing a live firewall,
activating a release, rebooting the guest, enabling boot startup, and any
retention deletion each require their exact target and separate live approval.

## Platform and ownership record

The private site record names the infrastructure owner, trial operator,
platform owner, backup/restore owner, certificate/access owner, capacity owner,
incident contact, engineer-feedback owner, and project approver. It also records:

- Ubuntu Server 22.04.x amd64, Python 3.10, ROS 2 Humble, PostgreSQL 14,
  FFmpeg/ffprobe, Nginx, NFS client, and nftables package versions;
- VM identity, recovery point, vCPU/RAM/disk facts, UTC/time sync, stable MAC,
  IPv4 and IPv6 routes, Start on Boot, console policy, and shutdown budget;
- exact source export/mount and server-side read-only evidence;
- exact derived filesystem UUID, capacity basis, warning/rejection thresholds,
  reservation/quota, and growth procedure;
- database roles, protected backup target, RPO, retention, encryption, restore
  owner, and coherent derived-recovery rule;
- TLS issuer/expiry/renewal, individual access owners, grant/revoke/expiry, and
  upstream plus guest firewall evidence; and
- the TrueNAS release-risk decision, configuration backup, recovery route, and
  maintenance/escalation owner.

Ubuntu 22.04 standard security maintenance and ROS 2 Humble support end in May
2027. The named platform owner must decide the supported successor by
2027-01-31. Ubuntu extended maintenance does not extend ROS Humble.

## Reviewed runtime inventory

Resolve and save exact APT versions before installation; do not use an
unrecorded upgrade during commissioning. [`deploy/apt-packages.in`](../deploy/apt-packages.in)
is the narrow package-name inventory. The application imports only `rclpy`
serialization and `sensor_msgs` Image/Imu from ROS; it does not require a ROS
desktop installation.

| Component | Role and source | Licence implication to retain in evidence |
|---|---|---|
| Ubuntu 22.04/Python 3.10 | Approved Ubuntu repositories; guest and interpreter | Ubuntu packages are individually licensed; Python is PSF-licensed |
| ROS 2 Humble `rclpy`, `sensor_msgs` | Approved ROS repository; CDR deserialization and messages | Primarily Apache-2.0; preserve the resolved package notices |
| FFmpeg/ffprobe with `libx264` | Approved Ubuntu repository; fixed H.264/yuv420p preview validation | Ubuntu build is GPL-enabled; retain package copyright/licence data |
| PostgreSQL 14 client/server | Approved Ubuntu repository; six-table V1 metadata and custom dumps | PostgreSQL Licence plus packaged dependencies |
| Nginx/OpenSSL/apache2-utils | Approved Ubuntu repository; TLS proxy and individual htpasswd fallback | Preserve package notices and site certificate policy |
| nfs-common/nftables/curl | Approved Ubuntu repository; mount, firewall, drain/health tools | Preserve resolved package notices |
| Python wheels | Approved Python repository copied into a checksummed wheelhouse | `LICENSES.json` records wheel metadata; PyAV is BSD-3-Clause and psycopg binary is LGPL-3.0-only |

The wheelhouse also records the sanitized repository label, CPython version,
Ubuntu 22.04 amd64/CPython 3.10 target and the compatible manylinux 2.28/2.17
wheel tags, every wheel checksum, and every declared licence. Review bundled
licences (not only the short metadata field) before distributing the release.

## Gate 0 read-only audit

Capture outputs in the protected site evidence location, not Git or chat. These
commands do not traverse the recording tree or write-probe the source:

```bash
hostnamectl
timedatectl show
uname -a
lsb_release -a
lscpu
free -h
lsblk -o NAME,PATH,TYPE,SIZE,FSTYPE,UUID,MOUNTPOINTS,RO
ip -brief address
ip -4 route
ip -6 route
ss -lntup
systemctl is-enabled systemd-timesyncd.service
```

The administrator supplies saved TrueNAS export configuration proving exact
path, dataset-versus-directory status, read-only mode, VM-only allow entry,
NFS version/security, root mapping, bind/firewall scope, overlapping exports,
and known consumers. No `touch`, `mkdir`, SQLite open, reindex, or repair command
is a valid read-only test.

## Build a release off the VM

Use an approved Ubuntu 22.04/CPython 3.10 amd64 builder. Network access is
allowed only while constructing the reviewed wheelhouse from the approved
repository. The VM install itself is offline with respect to Python dependency
resolution.

```bash
deploy/scripts/build-wheelhouse \
  /protected/staging/wheelhouse-v1-RELEASE \
  APPROVED_REPOSITORY_LABEL
deploy/scripts/build-release \
  v1-RELEASE BUILD_OPERATOR \
  /protected/staging/wheelhouse-v1-RELEASE \
  /protected/staging/release-v1-RELEASE
sha256sum --check \
  /protected/staging/release-v1-RELEASE/v1-RELEASE.tar.gz.sha256
cd /protected/staging/release-v1-RELEASE
sha256sum --check --strict INSTALLER-SHA256SUMS
```

Expected results are a checksummed wheelhouse and one release archive with a
sidecar checksum. `build-release` refuses dirty or untracked source. The current
accepted project work is intentionally uncommitted, so creating the first real
release is blocked until the user separately approves a commit or another
reviewed clean source identity. Prompt 3 alone is not commit approval.

Archive installation rechecks the supplied checksum, rejects links, devices,
escapes, oversized content, and unexpected roots, checks every release and
wheelhouse file, installs into a new directory, runs `pip check`, and never
replaces an existing release.

## Render the private guest change set

Render these templates into a protected staging directory, replace every
documentation value, and attach their checksums to the live change review:

- `environment.example`, `migration-environment.example`, and
  `backup-environment.example`;
- source and derived mount templates, with names returned by
  `systemd-escape --path --suffix=mount` for the exact mountpoints;
- API, worker, preflight, migration, and target units;
- Nginx site and proxy-header files; and
- the nftables template with exact approved IPv4 and IPv6 allow sets.

The rendered application listener remains `127.0.0.1:8000`; PostgreSQL remains
on its Unix socket or loopback. The Nginx hostname, origin, listen addresses,
certificate paths, and individual credential files must agree. Documentation
addresses and `REPLACE_WITH` values make validation fail.

Run before mutation:

```bash
deploy/scripts/validate-firewall /protected/staging/rosbag-analyser.nft
deploy/scripts/validate-proxy \
  /protected/staging/rosbag-analyser.conf \
  APPROVED_HOSTNAME APPROVED_IPV4 APPROVED_IPV6
```

Expected: sanitized firewall and proxy validation success. Firewall validation
is only a no-apply syntax/contract check. The operator must still compare the
rule semantics with upstream IPv4/IPv6 policy and prove console/recovery access.

## Base guest and service identities

After the exact command review, install only the resolved packages in
`deploy/apt-packages.in` from approved configured repositories. Save
`apt-cache policy` before installation and `dpkg-query -W` afterward. Do not
curl-pipe repository installers.

Create one non-login runtime identity and a distinct migration identity:

```bash
sudo useradd --system --home-dir /nonexistent --no-create-home \
  --shell /usr/sbin/nologin --user-group rosbag-analyser
sudo useradd --system --home-dir /nonexistent --no-create-home \
  --shell /usr/sbin/nologin --gid rosbag-analyser rosbag-analyser-migrate
sudo install -d -o root -g rosbag-analyser -m 0750 /etc/rosbag-analyser
sudo install -d -o root -g root -m 0755 \
  /opt/rosbag-analyser /opt/rosbag-analyser/releases \
  /opt/rosbag-analyser/staging /srv/rosbag-analyser/source
sudo install -d -o root -g postgres -m 0750 /var/backups/rosbag-analyser
```

Expected: neither account has a password, login shell, sudo access, or writable
home. Releases and configuration remain root-owned.

## PostgreSQL roles and schema

Use three distinct login roles: runtime, migration/owner, and backup. The
private role-creation SQL and generated passwords are reviewed and executed by
the database administrator; they are never pasted into shell history or Git.
PostgreSQL listens only on `/run/postgresql` or loopback and `pg_hba.conf`
allows only the intended local role/database pairs.

The migration role owns the trial database. The runtime role receives only
connect, schema usage, table DML, and sequence usage. The backup role receives
connect, schema usage, and read access. Set matching default privileges for
objects subsequently created by the migration owner. None is a superuser; the
runtime role cannot create a database or schema.

The three root-owned pgpass files are mode 0600 and contain exactly one local
entry. Application, migration, and backup environment files contain URLs with
role names but no password. Validate without printing values:

After the candidate release has been installed but before migration or
activation, validate without printing values:

```bash
sudo /opt/rosbag-analyser/releases/v1-RELEASE/deploy/scripts/validate-site \
  /etc/rosbag-analyser/application.env \
  /etc/rosbag-analyser/migration.env \
  /etc/rosbag-analyser/backup.env \
  /etc/rosbag-analyser/runtime.pgpass \
  /etc/rosbag-analyser/migration.pgpass \
  /etc/rosbag-analyser/backup.pgpass \
  /etc/rosbag-analyser/tls/fullchain.pem \
  /etc/rosbag-analyser/tls/private.key \
  /etc/rosbag-analyser/access/engineers.htpasswd \
  /etc/rosbag-analyser/access/operators.htpasswd \
  APPROVED_HOSTNAME
```

Expected: one sanitized success line. The check rejects symlinks, unsafe modes,
non-root ownership, placeholder/empty values, malformed pgpass/htpasswd files,
identical engineer/operator sets, invalid keys, and certificates expiring in
seven days.

## Mounts and derived ownership

The administrator first proves the server-side source export is exact and
read-only. Install the reviewed client unit with
`ro,nosuid,nodev,noexec,_netdev` and the approved NFS version. The empty local
mountpoint is root-owned and not used as a fallback. Start the mount, then use
only metadata tools:

```bash
systemctl start 'srv-rosbag\x2danalyser-source.mount'
findmnt --mountpoint /srv/rosbag-analyser/source \
  --output TARGET,SOURCE,FSTYPE,OPTIONS,MAJ:MIN
```

Expected: exact target, exact dedicated export, `nfs4`, and `ro,nosuid,nodev,noexec`.
Do not list the source directory before the real-data annex authorizes the
before manifest.

The derived filesystem is separate. Formatting is destructive: generate its
exact `mkfs` command only after the approved `/dev/disk/by-id` target, `lsblk`
facts, recovery point, and confirmation are attached to the live review. Never
copy a placeholder formatting command. After the reviewed filesystem is
mounted `rw,nosuid,nodev`:

```bash
sudo install -o root -g root -m 0444 /dev/stdin \
  /var/lib/rosbag-analyser/derived/.rosbag-analyser-derived-v1 \
  <<<'rosbag-analyser-derived-v1'
sudo install -d -o rosbag-analyser -g rosbag-analyser -m 0750 \
  /var/lib/rosbag-analyser/derived/rosbag-analyser
findmnt --mountpoint /var/lib/rosbag-analyser/derived \
  --output TARGET,SOURCE,FSTYPE,OPTIONS,MAJ:MIN,SIZE,AVAIL
```

The marker is root-owned and immutable to the service; only the
`rosbag-analyser` child is application-writable. Temporary and final artifacts
therefore remain on one filesystem for atomic rename. The configured rejection
threshold is the larger operational constraint represented by the byte and
percentage settings. Low space pauses claims and rejects new preparation; it
does not delete valid output.

## Install, migrate, and activate a candidate

Do not enable boot startup yet. Copy the reviewed archive and checksum into a
root-controlled staging location, then:

```bash
sudo /protected/staging/release-v1-RELEASE/install-release \
  v1-RELEASE \
  /protected/staging/release-v1-RELEASE/v1-RELEASE.tar.gz \
  EXPECTED_SHA256
sudo install -o root -g rosbag-analyser -m 0640 \
  /protected/site/application.env /etc/rosbag-analyser/application.env
sudo install -o root -g rosbag-analyser -m 0640 \
  /protected/site/migration.env /etc/rosbag-analyser/migration.env
sudo install -o root -g root -m 0600 \
  /protected/site/backup.env /etc/rosbag-analyser/backup.env
sudo install -o root -g root -m 0600 \
  /protected/site/runtime.pgpass /etc/rosbag-analyser/runtime.pgpass
sudo install -o root -g root -m 0600 \
  /protected/site/migration.pgpass /etc/rosbag-analyser/migration.pgpass
sudo install -o root -g root -m 0600 \
  /protected/site/backup.pgpass /etc/rosbag-analyser/backup.pgpass
sudo install -o root -g root -m 0644 \
  /protected/site/srv-rosbag-analyser-source.mount \
  '/etc/systemd/system/srv-rosbag\x2danalyser-source.mount'
sudo install -o root -g root -m 0644 \
  /protected/site/var-lib-rosbag-analyser-derived.mount \
  '/etc/systemd/system/var-lib-rosbag\x2danalyser-derived.mount'
sudo install -o root -g root -m 0644 \
  /opt/rosbag-analyser/releases/v1-RELEASE/deploy/systemd/*.service \
  /opt/rosbag-analyser/releases/v1-RELEASE/deploy/systemd/rosbag-analyser.target \
  /etc/systemd/system/
sudo install -d -o root -g root -m 0755 /etc/systemd/system/nginx.service.d
sudo install -o root -g root -m 0644 \
  /opt/rosbag-analyser/releases/v1-RELEASE/deploy/systemd/nginx-rosbag-analyser.conf \
  /etc/systemd/system/nginx.service.d/rosbag-analyser.conf
# Run the complete validate-site command from the PostgreSQL section here.
sudo systemctl daemon-reload
sudo systemctl start postgresql.service
sudo systemctl start 'srv-rosbag\x2danalyser-source.mount'
sudo systemctl start 'var-lib-rosbag\x2danalyser-derived.mount'
sudo systemctl start rosbag-analyser-migrate@v1-RELEASE.service
sudo deploy/scripts/activate-release v1-RELEASE
sudo systemctl start rosbag-analyser-preflight.service
```

Expected: the migration runs once under the repository advisory lock, exactly
six V1 domain tables validate, the release pointer switches atomically, and
preflight reports release/dependency identity, schema, exact mounts, capacity,
ROS imports, and `libx264`. API and worker startup never migrate.

The default first trial uses a new empty database. Do not import a development
database without the separately reviewed coherent database-plus-derived-state
annex.

## Nginx, firewall, and first start

Install root-owned rendered Nginx files. Remove/disable the default site, but do
not start Nginx until access policy is proven. Run `nginx -t`; expected output
ends with `test is successful`.

```bash
sudo install -o root -g root -m 0644 \
  /protected/site/rosbag-analyser-proxy-headers.conf \
  /etc/nginx/rosbag-analyser-proxy-headers.conf
sudo install -o root -g root -m 0644 \
  /protected/site/rosbag-analyser.conf \
  /etc/nginx/conf.d/rosbag-analyser.conf
sudo nginx -t
```

The template accepts only the approved hostname and GET/HEAD/POST, rejects
cross-origin POST, bounds bodies and timeouts, rate-limits state changes,
separates operator rescans from engineer preparation/retry, disables API docs,
strips upstream Authorization and untrusted forwarding, disables proxy caching,
and proxies media through the application so Range/If-Range/ETag identity checks
remain authoritative.

Before applying nftables, save the current rules, prove the recovery console,
schedule automatic rollback, and test the rollback command. Apply only the
reviewed file. From approved and denied IPv4 and IPv6 vantage points, prove SSH
admin and HTTPS trial allow rules plus denial of NFS, 8000, 5432, VNC, and all
unlisted ingress. Keep the upstream firewall as defence in depth.

Start locally first:

```bash
sudo systemctl start rosbag-analyser-api.service
sudo systemctl start rosbag-analyser-worker.service
curl --fail --silent http://127.0.0.1:8000/health/live
curl --fail --silent http://127.0.0.1:8000/health/ready
sudo /opt/rosbag-analyser/current/deploy/scripts/smoke-check
```

Expected: liveness contains only `alive` and release identity. Readiness reports
separate sanitized capabilities. The smoke check observes saved state before
and after and fails if it creates a job. Only after local checks pass may Nginx
start and authenticated same-origin checks run.

## Planned upgrade sequence

1. Record active release/schema, mounts, capacity, services, queue, running job,
   rollback class, maintenance owner, and approved window.
2. Stop Nginx to close all engineer writes, then run `drain-worker`. Queued jobs
   remain persistent; the command waits only for the running job.
3. Install and fully preflight the candidate beside the active release.
4. With `PGPASSFILE` pointing to the backup credential and the backup
   environment loaded, run `backup-database BACKUP_DIRECTORY RELEASE_ID`.
   Copy the verified custom dump to the encrypted approved off-VM target and
   record its checksum/retention; a same-pool copy is not independent recovery.
5. Stop worker, then API. Run the candidate migration unit exactly once.
6. Activate the candidate pointer, start API and worker while Nginx remains
   stopped, restart the preflight one-shot, and run smoke checks including an
   approved saved recording ID.
7. Verify zero implicit jobs, catalog/detail, overview, IMU, saved artifacts,
   HEAD, byte Range, If-Range/ETag, and stale identity behavior.
8. Start Nginx only after acceptance. Retain the previous release and exact
   configuration mapping until the user accepts the upgrade.

Every candidate is classified before activation as either code-compatible with
the post-migration schema or database-restore rollback. Never improvise a down
migration. Database restore is coherent only with the selected derived rule:
either a quiesced database-plus-volume snapshot, or explicit invalidation and
regeneration of absent files.

## Backup, restore, and rollback

Create a custom dump daily and before every schema change. Every dump must pass
`pg_restore --list`, be copied encrypted off VM, and have a recorded owner,
RPO, retention/expiry, and failure alert. A VM or ZFS snapshot alone is not a
database-consistent backup.

Test a real restore before trial admission:

```bash
sudo install -o postgres -g postgres -m 0400 \
  /protected/backup/VERIFIED.dump \
  /var/backups/rosbag-analyser/restore-input.dump
sudo -u postgres env \
  ROS_BAG_ANALYSER_ADMIN_DATABASE_URL='postgresql:///postgres?host=/run/postgresql' \
  /opt/rosbag-analyser/current/deploy/scripts/restore-disposable-database \
  /var/backups/rosbag-analyser/restore-input.dump \
  rosbag_analyser_restore_CASE
```

Expected: a new prefixed database is created and restored; an existing target
is never replaced. Validate its six-table schema and representative saved rows.
Dropping the disposable database afterward is a separate destructive command
requiring exact approval.

For code-compatible rollback, stop Nginx, drain, stop worker/API, activate the
recorded previous release, start locally, smoke-test, then reopen Nginx. For
database-restore rollback, keep traffic closed, preserve the failed state for
diagnosis, create a new database from the verified dump, apply the recorded
derived-state rule, switch configuration atomically, then preflight and smoke.

## Interruption, outage, and capacity response

- Planned maintenance stops new requests at Nginx, drains the running job, then
  stops worker before API.
- Host/emergency shutdown sends SIGTERM. The worker finishes only if the active
  synchronous call returns inside the measured guest/NAS budget; otherwise
  systemd may force-stop it. Next startup marks only the abandoned running job
  interrupted and cleans only its proven job workspace. Retry is explicit.
- PostgreSQL or trusted-derived loss makes core readiness fail while liveness
  stays alive. Do not restart-loop the process.
- Source loss disables source access, rescan, and new preparation while saved
  catalog and valid ready artifacts remain available.
- Low derived space keeps core readiness and valid artifact delivery available,
  rejects new queue insertion, and pauses before worker claim. Expand storage
  through the infrastructure owner; do not delete ready output automatically.
- Full-disk, wrong-mount, NFS-loss, database-loss, and forced-interruption drills
  use disposable substitutes until the exact live drill is separately approved.

## Explicit rescan and queue operations

Starting a service or target never rescans. An operator performs the first
explicit rescan only after the approved before inventory. Use the operator
identity through the same-origin HTTPS route, or the existing documented local
operator path. A scan creates no jobs. If it is incomplete, the prior successful
generation remains current.

Use `/api/v1/processing/overview` for worker state and queue facts. A failed or
interrupted job is retried only through its explicit retry route, which
recomputes current identity. Never edit job rows manually.

## Logs and support

```bash
systemctl status rosbag-analyser.target --no-pager
journalctl -u rosbag-analyser-api.service --since today --no-pager
journalctl -u rosbag-analyser-worker.service --since today --no-pager
/opt/rosbag-analyser/current/deploy/scripts/collect-support-bundle \
  /protected/evidence/support-CASE
```

Application formatters redact database URLs, secret fields, and absolute paths.
Raw journal access remains operator-only. The support bundle deliberately omits
journal messages and environments; it includes bounded timestamp/priority/unit
metadata, sanitized health, service states, tool versions, and checksums. Review
it manually before sharing. Nginx uses the distribution's bounded log rotation;
Authorization is never forwarded upstream or added to access logs.

## Real-data acceptance and boot proof

After the annex is approved, the first project-controlled content read is:

```bash
rosbag-analyser-source-manifest \
  --source-root APPROVED_SOURCE_ROOT \
  --output PROTECTED_EVIDENCE_BEFORE \
  --max-depth APPROVED_DEPTH --max-entries APPROVED_ENTRIES
```

The command follows no symlinks, hashes no payload, records only relative name,
kind, size, and nanosecond mtime, is bounded, and refuses output inside source
or replacement of existing evidence. Then complete Prompt 3 live matrix items
1–15 for only the named cases. Capture the final manifest on success or failure
and compare digests and entries exactly.

Only after pre-boot checks pass:

```bash
sudo systemctl enable rosbag-analyser.target
sudo systemctl reboot
```

Reboot needs separate live confirmation. After the guest returns, prove mount
identity, PostgreSQL, migration gate, API, one worker, proxy, saved state, queue,
and zero implicit work. Verify the administrator-owned TrueNAS Start on Boot
setting from saved configuration; do not reboot the NAS host. Observe host-level
autostart at its next independently approved maintenance reboot.

## Maintenance schedule

- Daily: backup result/off-VM copy, readiness capabilities, capacity threshold,
  certificate/credential expiry alerts, failed/interrupted jobs.
- Weekly: protected log review, restore queue/backup alerts, OS/ROS/FFmpeg/
  PostgreSQL/Nginx security notices, trial access membership and revocations.
- Monthly: disposable database restore, capacity trend/growth decision,
  recovery/contact check, patch/reboot window, and runbook exercise.
- By 2027-01-31: platform owner records the supported Ubuntu/ROS migration
  decision. No unsupported continuation is implied.

Grant individual engineer access with an owner and expiry; communicate the URL
out of band. Revoke by removing that identity at the approved proxy or
htpasswd, validate Nginx, reload it, and test denial. Renew TLS with the issuer's
approved process, validate files and `nginx -t`, reload, then check expiry and
both IP families.

## Retirement

Stop and disable Nginx access and `rosbag-analyser.target`, revoke individual
credentials, preserve the final database/config/release/support evidence, and
record service state. Do not unmount, detach, delete, drop, wipe, expire, or
destroy source, derived, database, backup, release, VM, dataset, zvol, snapshot,
or certificate data until the owner separately approves exact retention and
deletion targets. The source archive is never an application retirement target.
