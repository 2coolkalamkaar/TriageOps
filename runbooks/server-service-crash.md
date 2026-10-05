# Runbook: Server — systemd Service Failing / Crashing

## What it means
A systemd-managed service has failed to start or crashed after running. It may be in `failed`, `inactive`, or `activating` state, and `systemctl status` shows a non-zero exit code.

## Common root causes

1. **Configuration error** — invalid config file syntax (nginx, sshd, etc.).
2. **Missing dependency** — the service depends on another service or resource that is not ready.
3. **Port already in use** — the service cannot bind to its configured port.
4. **Permission error** — the service user cannot read config files or write to required directories.
5. **Binary not found** — the executable path in the unit file is wrong or the binary was deleted.
6. **Resource limits** — OOM kill, file descriptor limit hit, or CPU quota exceeded.
7. **Timeout on start** — `TimeoutStartSec` expired before the service signalled ready.

## Key signals to look for

```
systemctl status <service>:
  Active: failed (Result: exit-code)
  Active: failed (Result: signal)
  Main PID: <N> (code=exited, status=1/FAILURE)
  Main PID: <N> (code=killed, signal=KILL)

journalctl -u <service>:
  Any ERROR, FATAL, "address already in use", "permission denied", "not found"
```

## Diagnosis steps

```bash
# 1. Check service status (most useful first view)
systemctl status <service-name>

# 2. Get full logs for this service (last 100 lines)
journalctl -u <service-name> -n 100 --no-pager

# 3. Get logs since last boot
journalctl -u <service-name> -b --no-pager

# 4. Check service configuration file
systemctl cat <service-name>

# 5. Test config syntax (service-specific)
nginx -t                          # nginx
apache2ctl configtest             # apache
sshd -t                           # sshd
named-checkconf /etc/named.conf   # bind9

# 6. Check dependencies
systemctl list-dependencies <service-name>

# 7. Check if port is in use
ss -tulnp | grep <port>
```

## Fix patterns

**Configuration syntax error:**
```bash
# Fix the config file, then test syntax, then restart
sudo nginx -t
sudo systemctl restart nginx
```

**Permission error:**
```bash
# Check who owns the config/log directories
ls -la /etc/<service>/
ls -la /var/log/<service>/

# Fix ownership if needed
sudo chown -R <service-user>:<service-group> /var/log/<service>/
sudo chmod 750 /var/log/<service>/
```

**Service won't stop — restart cycle:**
```bash
# Stop, reset failed state, then start fresh
sudo systemctl stop <service>
sudo systemctl reset-failed <service>
sudo systemctl start <service>
```

**Reload without restart (if service supports it):**
```bash
sudo systemctl reload <service>
```

**Re-enable and start a disabled service:**
```bash
sudo systemctl enable --now <service>
```

## Prevention
- Use `systemctl enable <service>` to auto-start on boot.
- Configure `Restart=on-failure` and `RestartSec=5` in the unit file for resilience.
- Run `journalctl -f -u <service>` during deployments to watch for errors in real time.
- Use `systemd-analyze blame` to find slow-starting services causing dependency timeouts.
- Always test config syntax (`nginx -t`, `sshd -t`) before applying changes.
