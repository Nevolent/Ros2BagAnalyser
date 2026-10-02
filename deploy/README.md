# Deployment tools

The VM application is in use. This directory contains reusable tooling and
templates; active site configuration lives outside Git. Start with
[Operations](../docs/OPERATIONS.md) for checks, releases and recovery.

Use `./vm` from the repository root for deployment, status, logs and diagnostics
with reports returned to this PC. It reuses the existing `vm-deploy.env`; no
second connection setup or diagnostic installation is required.

| Files | Purpose |
| --- | --- |
| `environment.example` | Runtime roots, topics, bounds, mount and capacity settings |
| `migration-environment.example`, `backup-environment.example` | Separate privileged database roles |
| `source.cifs-credentials.example` | Placeholder mount credential format |
| `vm-deploy-environment.example` | Workstation settings for `./deploy-vm` |
| `apt-packages.in`, `runtime-requirements.in`, `build-requirements.in` | OS and Python dependency inputs |
| `release-contract.json` | Platform, schema and processor identities |
| `systemd/`, `nginx/`, `firewall/` | Service, access and mount templates |
| `scripts/build-wheelhouse`, `build-release`, `install-release`, `activate-release` | Checksummed immutable releases |
| `scripts/deploy-from-git`, `deploy_release.py` | Staging, backups, migration and activation for Git deployments |
| `scripts/validate-site`, `validate-proxy`, `validate-firewall` | Configuration validation |
| `scripts/drain-worker`, `run-service`, `smoke-check` | Service lifecycle and saved-state checks |
| `scripts/backup-database`, `restore-disposable-database`, `collect-support-bundle` | Recovery and support |

Render placeholders for the site. Keep credentials, certificates, mount
identities and backup destinations in protected private configuration.
Tooling does not administer the TrueNAS appliance.

## Read-only diagnostics

- `scripts/audit-recording-topics` compares metadata and SQLite topic definitions
  with configured front/IMU topics. Explicit paths or bounded `--all` produce
  JSON Lines without decoding message payloads.
- `scripts/analyze-front-header-timestamps` inspects selected image streams for
  encoding and timing issues. It reads payloads but creates no jobs or media.
- Installed `rosbag-analyser-bag-inventory` inventories metadata;
  `rosbag-analyser-source-manifest` captures lightweight source-change evidence.

Use `--help` for exact arguments and bounds. Reports go outside source and Git.
These tools remain useful after retirement of the original commissioning plans.
