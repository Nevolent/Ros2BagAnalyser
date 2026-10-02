# Deployment tools

Use [Operations](../docs/OPERATIONS.md) for deployment, diagnostics and recovery.
Site configuration and credentials stay outside Git.

| Files | Purpose |
| --- | --- |
| `environment.example` | Runtime roots, topics, limits, mounts and capacity |
| `migration-environment.example`, `backup-environment.example` | Privileged database settings |
| `source.cifs-credentials.example` | Mount credential format |
| `vm-deploy-environment.example` | Workstation settings for VM commands |
| `apt-packages.in`, `runtime-requirements.in`, `build-requirements.in` | Dependency inputs |
| `release-contract.json` | Platform, schema and processor identities |
| `systemd/`, `nginx/`, `firewall/` | Service, mount and access templates |
| `scripts/` | Build, installation, validation, deployment and recovery commands |

Read-only diagnostics:

- `scripts/audit-recording-topics` compares metadata and SQLite topic definitions.
- `scripts/analyze-front-header-timestamps` inspects image encoding and timing.
- `rosbag-analyser-bag-inventory` inventories metadata.
- `rosbag-analyser-source-manifest` records lightweight source inventories.

Use `--help` for arguments and bounds. Keep reports outside source storage and Git.
