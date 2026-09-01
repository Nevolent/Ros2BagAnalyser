# Gate 0 administrator handoff — sanitized template

Status: **INCOMPLETE** until every owner and evidence reference is filled in a
private operator record and approved by the administrator and project owner.
Do not put private addresses, paths, UUIDs, credentials, or certificate details
in this repository copy.

| Area | Decision/evidence reference | Owner | Approved date |
|---|---|---|---|
| VM identity and clean-base recovery point | PENDING | PENDING | PENDING |
| Patched Ubuntu Server 22.04 amd64, UTC/time sync, SSH keys, no remote root/GUI | PENDING | PENDING | PENDING |
| vCPU topology, fixed RAM, CPU mode, OS disk | PENDING | PENDING | PENDING |
| Start on Boot, orderly shutdown budget, detached ISO, console/recovery path | PENDING | PENDING | PENDING |
| Stable IPv4/IPv6 policy, admin path, engineer HTTPS path, DNS/NTP | PENDING | PENDING | PENDING |
| Exact existing SMB/CIFS share, VM/account entry, and read-only source mount | PENDING | PENDING | PENDING |
| Exact reserved-cache SMB-subdirectory writable mount evidence | PENDING | PENDING | PENDING |
| Cache capacity basis, threshold, snapshot/backup policy, and growth owner | PENDING | PENDING | PENDING |
| PostgreSQL ownership and least-privilege runtime/migration/backup credentials | PENDING | PENDING | PENDING |
| Protected off-VM backup destination, encryption, RPO, retention, restore owner | PENDING | PENDING | PENDING |
| TLS issuer/renewal, identity proxy or individual credentials, named trial group | PENDING | PENDING | PENDING |
| Upstream and guest default-deny IPv4/IPv6 firewall rules and recovery path | PENDING | PENDING | PENDING |
| TrueNAS release risk decision, config backup, recovery, maintenance/escalation | PENDING | PENDING | PENDING |
| Platform owner and supported-platform decision due no later than 2027-01-31 | PENDING | PENDING | PENDING |
| Real-data annex reference and approved processing window | PENDING | PENDING | PENDING |

The baseline is one socket/six cores/one thread per core, host CPU passthrough,
16 GiB fixed RAM, a 100 GiB OS disk, and the NAS-resident reserved cache folder.
Every variance is recorded and tested. Ubuntu 22.04 and ROS 2 Humble support end
in May 2027; Ubuntu extended maintenance does not extend ROS Humble.
