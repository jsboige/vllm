# fs-tier pruner — scheduled from inside WSL (systemd)

The KV fs tier (`/home/user/vllm/.kv-tier-fs`, Ubuntu WSL distro) has **no in-code eviction**:
without `fstier_pruner.py` it grows until the guest disk is full. That disk is shared with the
HF cache and the CoursIA CI runners (`coursia-runner.service`), so a dead pruner is an outage
for all of them, not only for the tier.

## Why systemd and not the Windows task

Until 2026-11-20 the pruner ran from the Windows scheduled task `fstier-prune`:
`wscript.exe` → `fstier-prune.vbs` → `pwsh.exe fstier_prune.ps1` → `wsl.exe … python3`.
On 2026-11-20 the Google Drive (DriveFS) drive G: hung on ai-01. From then on, new
`powershell.exe`/`pwsh.exe` processes, and then `wscript.exe` itself, hung at start-up and
could not be killed. The last pruner pass that completed was at 07:22Z. By 12:1xZ the tier
was 436.8 GB against its 250 GiB cap, and the guest disk had **0 bytes free on 1.08 TB**.
The engine logged `Errno 28` on its tier writes, and the CoursIA runners failed in ENOSPC,
which held `main-red` and blocked merges on every lane.

The pruner is pure Linux work, and none of those Windows layers was needed. The timer
runs it from inside the distro, so it keeps running when the Windows shell is unhealthy.

## Install (as root inside the distro)

```bash
S=/mnt/d/vllm/myia_vllm/scripts/monitoring/systemd
for f in fstier-prune.service fstier-prune.timer; do tr -d '\r' < $S/$f > /etc/systemd/system/$f; done
systemctl daemon-reload
systemd-analyze verify /etc/systemd/system/fstier-prune.{service,timer}
systemctl start fstier-prune.service          # one real pass, check the state file
systemctl enable --now fstier-prune.timer
```

From Windows, wrap each step in `wsl.exe -d Ubuntu -u root --exec sh -c '…'`, with
`MSYS_NO_PATHCONV=1` from Git Bash. `tr -d '\r'` matters: systemd does not tolerate CRLF.

**One scheduler only.** Once the timer is enabled, keep the Windows task disabled
(`schtasks /change /tn fstier-prune /disable`). Two schedulers would run two pruners. The
`flock` makes that safe, but it is pointless.

## Verify

```bash
systemctl list-timers fstier-prune.timer --no-pager
journalctl -u fstier-prune.service -n 20 --no-pager
cat /mnt/d/vllm/myia_vllm/logs/fstier_state.json   # ts_utc fresh (< 35 min), errors_count
df -B1 /                                            # guest disk: must stay above the 40 GiB floor
```

## Rollback

```bash
systemctl disable --now fstier-prune.timer
rm /etc/systemd/system/fstier-prune.service /etc/systemd/system/fstier-prune.timer
systemctl daemon-reload
```

Then re-enable the Windows task: `schtasks /change /tn fstier-prune /enable`.
