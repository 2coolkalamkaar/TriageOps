# Runbook: Server — Disk Full / No Space Left on Device

## What it means
A filesystem has reached 100% utilisation. Any write operation (logs, temp files, database writes, package installs) will fail with "No space left on device". This is a P1/P2 issue — it can corrupt databases, stop services, and fill audit logs.

## Common root causes

1. **Log files not rotated** — application or system logs grew unboundedly.
2. **Temp files accumulating** — `/tmp`, `/var/tmp`, or application temp dirs not cleaned up.
3. **Large core dumps** — a crashing process wrote a core dump filling the disk.
4. **Docker image/layer accumulation** — unused images, containers, and volumes consuming space.
5. **Database growing** — database data files, WAL logs, or binlogs grew without archiving.
6. **Inode exhaustion** — disk has free blocks but no free inodes (too many small files).
7. **Snapshot/backup not cleaned up** — old LVM snapshots or backup archives not pruned.

## Key signals to look for

```
df -h:
  /dev/sda1  100%  (or very close)

dmesg / journalctl:
  "No space left on device"
  "EXT4-fs error ... ENOSPC"

application logs:
  "write: no space left on device"
  "errno 28 (ENOSPC)"
```

## Diagnosis steps

```bash
# 1. Check disk usage by filesystem
df -h

# 2. Check inode usage (a separate exhaustion problem)
df -i

# 3. Find the largest directories on the full filesystem (e.g. /)
du -sh /* 2>/dev/null | sort -rh | head -20

# 4. Drill into the biggest directory
du -sh /var/* 2>/dev/null | sort -rh | head -20
du -sh /var/log/* 2>/dev/null | sort -rh | head -10

# 5. Find very large individual files
find / -xdev -type f -size +100M 2>/dev/null | xargs ls -lh | sort -k5 -rh | head -20

# 6. Check for large log files
ls -lh /var/log/*.log 2>/dev/null
journalctl --disk-usage

# 7. Check for core dumps
find / -xdev -name "core" -o -name "core.*" 2>/dev/null
```

## Fix patterns — safe options first

**Rotate and compress old logs immediately:**
```bash
# Force logrotate
sudo logrotate -f /etc/logrotate.conf

# Truncate a specific log safely (do NOT delete while process has it open)
sudo truncate -s 0 /var/log/application.log
```

**Clear journal logs (systemd):**
```bash
# Keep only last 2 days of journal logs
sudo journalctl --vacuum-time=2d

# Or limit by size
sudo journalctl --vacuum-size=500M
```

**Remove core dumps:**
```bash
# List first
find / -xdev -name "core*" -type f 2>/dev/null

# Remove after confirming
sudo find / -xdev -name "core*" -type f -delete
```

**Clear temp files:**
```bash
sudo find /tmp -type f -atime +7 -delete
sudo find /var/tmp -type f -atime +7 -delete
```

**Docker cleanup (if Docker is running):**
```bash
# Safe: removes stopped containers, dangling images, unused networks
docker system prune

# More aggressive: also removes unused volumes
# docker system prune -a --volumes
# ⚠️ Check what will be removed first with --dry-run if supported
```

**APT/YUM package cache:**
```bash
sudo apt-get clean    # Debian/Ubuntu
sudo yum clean all    # RHEL/CentOS
```

## Prevention
- Configure `logrotate` for all application logs.
- Set `SystemMaxUse=1G` in `/etc/systemd/journald.conf`.
- Set up disk usage alerts at 75%, 85%, and 95%.
- Use LVM thin provisioning or cloud volume auto-expand where possible.
- Schedule regular `docker system prune` in cron for hosts running Docker.
- Set `ulimit -c 0` or `kernel.core_pattern=/dev/null` to disable core dumps in production.
