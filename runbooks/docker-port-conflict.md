# Runbook: Docker Port Already In Use / Bind Error

## What it means
Docker cannot start a container because the host port it needs to bind to is already occupied by another process. The container fails immediately at start.

## Common root causes

1. **Previous container still running or in "Exited" state with port held** — a stopped container may still hold the port mapping.
2. **Another service running on the host** — a system service (nginx, apache, another app) is already using that port.
3. **Previous container not properly cleaned up** — zombie container from a failed restart.
4. **Port conflict between docker-compose services** — two services mapped to the same host port.

## Key signals to look for

```
Error response from daemon: driver failed programming external connectivity on endpoint:
  Bind for 0.0.0.0:80 failed: port is already allocated

Error starting userland proxy: listen tcp4 0.0.0.0:8080: bind: address already in use
```

## Diagnosis steps

```bash
# 1. Find what is using the port
sudo lsof -i :<port>
# or
sudo ss -tulnp | grep :<port>
# or
sudo netstat -tulnp | grep :<port>

# 2. Check for stopped containers still holding ports
docker ps -a
docker ps -a --filter "status=exited"

# 3. List all port mappings in use by Docker
docker ps --format "table {{.Names}}\t{{.Ports}}"

# 4. Check docker-compose for port conflicts
cat docker-compose.yml | grep -A2 ports
```

## Fix patterns

**Remove the conflicting stopped container:**
```bash
docker ps -a  # find the container name/ID
docker rm <container-name>
```

**Kill the host process using the port:**
```bash
# Find the PID
sudo lsof -i :<port>
# Kill it gracefully
sudo kill -15 <pid>
# Only use kill -9 if kill -15 doesn't work after 5 seconds
```

**Change the host port mapping:**
```bash
# Change the host port (e.g. map to 8081 instead of 8080)
docker run -p 8081:8080 <image>

# In docker-compose.yml:
# ports:
#   - "8081:8080"
```

**Clean up all stopped containers:**
```bash
# Safe: only removes stopped (exited) containers
docker container prune
```

## Prevention
- Use `docker-compose down` (not just Ctrl+C) to properly remove containers.
- Document which ports each service uses in your README.
- Use a port registry or service discovery to avoid conflicts in complex environments.
- Consider using Docker networks with internal ports instead of host port mappings.
