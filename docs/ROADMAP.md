# Current priorities

The backend and VM deployment are in use. Work is now organized by useful
product changes, without the former numbered building blocks.

## Next: finish the frontend

- Evaluate the separately runnable React frontend against a bounded real workflow
  before making it the default. Keep the imported design as the visual reference
  and retain the existing served UI until that transition is approved.
- Resolve layout, navigation, selection, menus, and recording-level processing
  presentation across ordinary desktop sizes and narrow screens.
- Make loading, unavailable output, partial preparation, failures, and recovery
  clear. Preserve real API behavior and accessible interaction.
- Verify long-recording review and larger IMU bundles; keep graph rendering
  responsive with measured input bounds.

## Engineer release readiness

Use a representative engineer workflow as the release check: find a recording,
prepare it, understand the queue, review synchronized output, and recover from
an ordinary failure. Include keyboard use, responsive layouts, and real browser
playback. Keep evidence proportional to the change.

Confirm the current engineer access route and operational ownership from the
running site when preparing that release. Deployment is already working;
older documentation is not evidence of today's proxy, backup, or reboot state.
Record the actual release revision and any unresolved issue at that time.

## Maintenance

- Keep backup/restore, capacity, and upgrade instructions usable by an operator.
- Review the Ubuntu/ROS platform against the support boundary recorded in
  `deploy/release-contract.json` before planning upgrades.
- Add formats, topics, analysis tools, or worker capacity when an engineering
  need and measured limits justify them. These are future decisions, not bans.

This list is a priority guide, not a claim that remaining frontend or live
release checks were completed by the repository cleanup.
