# Historical backup

[legacy-docs-2026-09-19.tar.gz](legacy-docs-2026-09-19.tar.gz) preserves all 22
Markdown documents present before the cleanup, including V0 evidence, V1 plans,
execution prompts, old contributor instructions, deployment checklists, the
local VM guide and JetBrains notes. Original paths and contents are retained;
every archived file was verified against its original bytes.

These are historical evidence, not current status or instructions. Their gates,
prototype labels and old visual references are superseded by today's README
and documents. Extract only when investigating history:

```bash
tar -tzf docs/history/legacy-docs-2026-09-19.tar.gz
tar -xzf docs/history/legacy-docs-2026-09-19.tar.gz -C /path/to/empty-review-directory
```

SHA-256: `f62e3aed6b669dff81092f199ca436106d0fd660f98136bca45a720f6795ddae`

The pre-cleanup Git baseline is `2e597a7`; shared history is retained. On the
original workstation, ignored `.local-backup/2026-09-19/` also holds a verified
Git bundle, retired frontend files, JetBrains snapshots/import debris and the
private inventory moved out of the root. These local backups are not distributed.
The current JetBrains workspace is tracked; generated fixtures/screenshots
remain ignored.
