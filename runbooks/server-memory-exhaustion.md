# Runbook: Server — High Memory Usage / Out of Memory

## What it means
The server is running critically low on RAM. The Linux OOM killer may activate, processes will be killed, and swap (if enabled) will be under heavy pressure, severely degrading performance.

## Common root causes

1. **Memory leak in a long-running process** — gradual growth over hours or days.
2. **Traffic spike** — more requests than expected causing proportional memory use.
3. **Large data processing job** — batch job loading too much into memory.
4. **Too many processes** — too many worker threads/processes configured.
5. **Kernel cache not being released** — appears as low "free" memory but is often safe (cache is reclaimed on demand).
6. **Misconfigured JVM heap** — Java process with `-Xmx` too large for the host.
7. **Memory overcommit misconfiguration** — `vm.overcommit_memory` settings allowing too much allocation.

## Key signals to look for

```
free -m:
  available < 200MB (critical)
  swap used significantly

dmesg:
  "Out of memory: Kill process <pid> <name>"
  "oom_kill_process"

top / htop:
  Process with MEM% very high
  Load average very high
```

## Diagnosis steps

```bash
# 1. Check memory overview
free -m
# Note: "available" is the important number, not "free"

# 2. Find the top memory consumers
ps aux --sort=-%mem | head -20

# 3. Check if OOM killer has fired
dmesg | grep -i "out of memory" | tail -20
journalctl -k | grep -i "oom"

# 4. Check swap usage
swapon --show
vmstat -s | grep swap

# 5. Check memory details by process (PID from ps)
cat /proc/<pid>/status | grep -E "VmRSS|VmSwap|VmSize"

# 6. Check for memory fragmentation or pressure
cat /proc/meminfo | grep -E "MemFree|MemAvailable|SwapFree|Cached|Buffers"
```

## Fix patterns

**Identify and restart a leaking process:**
```bash
# Monitor memory growth over time
watch -n 5 'ps aux --sort=-%mem | head -10'

# Gracefully restart the leaking service (safer than kill)
sudo systemctl restart <service-name>
```

**Free up page cache (safe, kernel will reclaim automatically — this is manual flush):**
```bash
sync && echo 3 | sudo tee /proc/sys/vm/drop_caches
# ⚠️ This causes a brief I/O spike. Use only in an emergency.
```

**Kill a runaway process (escalating approach):**
```bash
# Try graceful shutdown first
kill -15 <pid>

# If still alive after 5 seconds, hard kill
# kill -9 <pid>
# ⚠️ SIGKILL — no cleanup, may corrupt application state
```

**Reduce worker count in config (example: nginx):**
```bash
# In /etc/nginx/nginx.conf:
# worker_processes auto;  ← set to a specific number if auto is too high
sudo nginx -t && sudo systemctl reload nginx
```

**Add swap as emergency buffer (temporary measure):**
```bash
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
# To make permanent, add to /etc/fstab
```

## Prevention
- Set memory limits on all processes (Docker: `--memory`, systemd: `MemoryLimit=`).
- Configure monitoring alerts at 75%, 85%, and 95% memory utilisation.
- Enable swap as a safety net, even on servers with large RAM.
- Use `systemd-oomd` or `earlyoom` for faster, more graceful OOM handling.
- Profile memory usage in staging under realistic load before deploying.
