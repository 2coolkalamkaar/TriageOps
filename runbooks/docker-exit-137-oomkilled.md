# Runbook: Docker OOMKilled / Exit Code 137

## What it means
The container process was killed by the Linux Out-Of-Memory (OOM) killer, which sends SIGKILL (signal 9). Exit code 137 = 128 + 9. This happens when the container's memory usage exceeds its configured limit, or when the host runs out of memory.

## Common root causes

1. **Memory limit too low** — the application needs more memory than the container's `--memory` limit allows.
2. **Memory leak in the application** — memory usage grows unboundedly over time.
3. **Spike in traffic / workload** — a sudden increase in requests causes temporary memory spikes.
4. **Large dataset loaded into memory** — batch jobs or analytics tasks load more data than available.
5. **Host OOM** — the host itself ran out of memory, killing containers to free resources.

## Key signals to look for

```
docker inspect <container>:
  "OOMKilled": true
  "ExitCode": 137

dmesg or /var/log/syslog:
  Out of memory: Kill process <pid> <name> score <n> or sacrifice child

docker stats:
  MEM USAGE / LIMIT shows near 100%
```

## Diagnosis steps

```bash
# 1. Check if OOMKilled
docker inspect <container-name> | grep -A5 '"State"'

# 2. Check memory usage history
docker stats --no-stream <container-name>

# 3. Check host memory
free -m
cat /proc/meminfo

# 4. Check kernel OOM logs
dmesg | grep -i "out of memory"
dmesg | grep -i "oom"

# 5. Check current container memory limits
docker inspect <container-name> | grep -i memory
```

## Fix patterns

**Increase memory limit:**
```bash
# Stop and recreate with higher limit
docker stop <container-name>
docker run --memory="1g" --memory-swap="1g" ... <image>

# Or in docker-compose.yml:
# services:
#   app:
#     mem_limit: 1g
```

**Diagnose memory leak (attach to running container):**
```bash
# Check process memory inside container
docker exec <container> cat /proc/1/status | grep VmRSS

# Run heap profiling if app supports it (language-specific)
```

**Host OOM — find the memory hog:**
```bash
# Sort processes by memory use
ps aux --sort=-%mem | head -20

# Check docker container stats
docker stats --no-stream
```

## Prevention
- Always set explicit `--memory` limits on containers.
- Set `--memory-swap` equal to `--memory` to disable swap (avoids slow OOM death).
- Configure alerts on memory usage > 80%.
- Use memory profiling in staging before production deployment.
- Implement graceful degradation (e.g. request queue limits) to prevent spikes.
- In Kubernetes, set both `resources.requests.memory` and `resources.limits.memory`.
