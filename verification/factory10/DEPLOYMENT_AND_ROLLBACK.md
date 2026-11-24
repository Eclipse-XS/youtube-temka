# Factory 10 deployment and rollback evidence

Both CPU and GPU Compose configurations validated. The candidate has a successful browser export, revision and proxy. An isolated SQLite rehearsal backed up a job from `ad16357`, opened the existing database with `ac32ab0`, restored the original backup in a separate directory, and reopened it with `ad16357`. Both copies returned `ok` from `PRAGMA quick_check` and retained the job and settings. The backup hash remained identical. See `verification/test-output/f10-deployment-state-20261125-012605/results.json` for the local evidence. The three supported launcher starts, full service lifecycle on upgrade and rollback, and real Drive delivery remain unverified. [Target environment and runner](TARGET_HARDWARE.md)

## Isolated deployment rehearsal

1. Use a separate checkout at the tested commit. Use a unique `COMPOSE_PROJECT_NAME`, unused loopback ports, independent data and scratch directories, and a private test token. Follow the existing Windows launcher setup. [Factory deployment](../../docs/FACTORY_DEPLOYMENT.md)
2. Run `.\scripts\start-factory.ps1 -Role Controller -Rebuild` and the same command with `-Status` in the isolated checkout. Verify controller and browser readiness, Ollama inventory, and persistent job history. Stop the idle test stack with `.\scripts\stop-factory.ps1 -Role Controller` between three launch attempts. Record each outcome.
3. Before testing the upgrade, run `docker compose --profile controller exec -T controller python -m factory.deployment backup`. Preserve the SQLite backup and copies of test settings and asset directories outside the active test data. Save the old and candidate commit and image identities. Keep any credentials in their existing read-only mounts.
4. In the isolated project, start the tested candidate and confirm that existing jobs and settings remain available, `PRAGMA quick_check` reports `ok`, and a previously approved local timeline can be reopened and replayed.
5. For rollback, stop the idle test stack. Launch the original build in another isolated directory and use copies of the pre-upgrade backup and retained settings and assets. Verify the same database, browser and playback checks. Record the backup hash, the old commit and the replay outcome.

## Private Drive verification

Use the existing authorized-user `DRIVE_TOKEN_FILE` or the existing legacy desktop client and token mounts with `DRIVE_OAUTH_CLIENT_FILE` and `DRIVE_OAUTH_TOKEN_FILE`. A private `DRIVE_PARENT_ID` is required for the acceptance runner. Set `"drive": true` on one authorized Shorts job and one authorized Longs job in the manifest, then append `--enable-drive` to the held-out command. The application checks folder permissions and verifies remote size and MD5 for the uploaded files. `cloud_verified` must be true for both job types. Preserve the local outputs and remote evidence privately. Automatic publishing is disabled by the runner.
