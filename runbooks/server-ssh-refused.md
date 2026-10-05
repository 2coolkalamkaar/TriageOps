# Runbook: Server — SSH Connection Refused / Timeout

## What it means
You cannot connect to a server via SSH. The connection is either refused immediately (port closed or service down) or times out (network issue or firewall).

## Common root causes

1. **sshd service not running** — the SSH daemon crashed or was stopped.
2. **Wrong port** — sshd was reconfigured to a non-standard port (not 22).
3. **Firewall blocking the connection** — iptables/nftables/ufw/security group blocking port 22 (or custom SSH port).
4. **Network connectivity issue** — routing problem between client and server.
5. **SSH host key mismatch** — server key changed (reinstall, snapshot restore) but client has old key cached.
6. **Authentication failure** — wrong key, expired password, or `AllowUsers`/`AllowGroups` restriction.
7. **MaxSessions / MaxStartups limit reached** — too many concurrent SSH connections.
8. **Disk full** — sshd cannot write to `/var/run/` or log files, refusing connections.

## Key signals to look for

```
ssh -v user@host:
  "Connection refused" → service down or firewall blocking
  "Connection timed out" → network/firewall issue
  "Host key verification failed" → key mismatch
  "Permission denied (publickey)" → auth issue
  "Too many authentication failures" → key agent offering wrong keys

Server-side (if accessible via console):
  systemctl status sshd
  journalctl -u sshd -n 50
```

## Diagnosis steps (from client)

```bash
# 1. Test basic connectivity (is the host reachable at all?)
ping -c 4 <host>

# 2. Test if port 22 is open (or the custom port)
nc -zv <host> 22
# or
telnet <host> 22

# 3. Verbose SSH to see exactly where it fails
ssh -vvv user@<host>

# 4. Try a different port if you know sshd uses non-standard port
ssh -p <custom-port> user@<host>
```

## Diagnosis steps (from server console / out-of-band access)

```bash
# 1. Check sshd status
systemctl status sshd

# 2. Check sshd logs
journalctl -u sshd -n 50 --no-pager

# 3. Check what port sshd is listening on
ss -tulnp | grep sshd

# 4. Check firewall rules
sudo iptables -L INPUT -n -v | grep 22
sudo ufw status verbose    # Ubuntu with ufw

# 5. Test sshd config syntax
sudo sshd -t

# 6. Check disk space (sshd fails if /var is full)
df -h
```

## Fix patterns

**sshd not running:**
```bash
sudo systemctl start sshd
sudo systemctl enable sshd
```

**Firewall blocking:**
```bash
# ufw
sudo ufw allow 22/tcp

# iptables
sudo iptables -I INPUT -p tcp --dport 22 -j ACCEPT

# Check cloud security groups (AWS/GCP/Azure) via console — cannot be fixed from CLI
```

**Host key mismatch (safe to fix on client):**
```bash
ssh-keygen -R <host>
# or remove the specific line from ~/.ssh/known_hosts
```

**sshd config broken — restore from backup or reset to default:**
```bash
sudo cp /etc/ssh/sshd_config.bak /etc/ssh/sshd_config
sudo sshd -t  # test before restarting
sudo systemctl restart sshd
```

## Prevention
- Keep a console/out-of-band access method (cloud console, IPMI, serial) in case SSH breaks.
- Never edit `/etc/ssh/sshd_config` without opening a second SSH session first, so you can recover.
- Use `sshd -t` to test config changes before applying.
- Set up SSH key authentication and disable password auth (`PasswordAuthentication no`).
- Monitor SSH service with a health check that alerts before it affects users.
