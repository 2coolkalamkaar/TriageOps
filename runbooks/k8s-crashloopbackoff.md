# Runbook: Kubernetes CrashLoopBackOff

## What it means
A pod is in `CrashLoopBackOff` when its container starts, crashes, and Kubernetes keeps restarting it with exponentially increasing delays. The container is not staying up long enough to be useful.

## Common root causes (in order of frequency)

1. **Application error / unhandled exception at startup** — the process exits non-zero immediately.
2. **Missing or incorrect environment variable** — app panics because a required config is absent.
3. **Missing ConfigMap or Secret** — the pod spec references a resource that does not exist in the namespace.
4. **Liveness probe misconfiguration** — the probe fires too early or targets the wrong path/port, killing a healthy container.
5. **OOMKilled (out of memory)** — container exceeds its memory limit, kernel kills it, exit code 137.
6. **Permission error** — container cannot write to a volume or read a mounted file.
7. **Bad image / corrupted entrypoint** — image was built incorrectly or the command does not exist.

## Key signals to look for

```
kubectl describe pod <name>:
  State: Waiting, Reason: CrashLoopBackOff
  Last State: Terminated, Exit Code: <N>
  Restart Count: <high number>

kubectl logs <pod>:
  Any ERROR or FATAL line near the end
  "panic:", "fatal:", "Error: ...", "SIGKILL", "OOMKilled"
```

## Diagnosis steps

```bash
# 1. Get pod status and events
kubectl describe pod <pod-name> -n <namespace>

# 2. Get logs from the current (crashing) container
kubectl logs <pod-name> -n <namespace>

# 3. Get logs from the PREVIOUS run (often more useful for crash diagnosis)
kubectl logs <pod-name> -n <namespace> --previous

# 4. Check for missing ConfigMap or Secret references
kubectl get configmap -n <namespace>
kubectl get secret -n <namespace>

# 5. Describe the deployment to see resource limits and env vars
kubectl describe deployment <deployment-name> -n <namespace>
```

## Exit code reference

| Exit Code | Meaning |
| --- | --- |
| 1 | Application error (generic) |
| 2 | Misuse of shell command |
| 126 | Permission denied / not executable |
| 127 | Command not found |
| 128 + N | Killed by signal N |
| 137 | SIGKILL (OOMKilled or manual kill) |
| 143 | SIGTERM (graceful shutdown) |

## Fix patterns

**Missing environment variable:**
```bash
kubectl set env deployment/<name> MY_VAR=value -n <namespace>
# or edit the deployment manifest
kubectl edit deployment <name> -n <namespace>
```

**Missing ConfigMap/Secret:**
```bash
kubectl create configmap <name> --from-file=config.yaml -n <namespace>
kubectl create secret generic <name> --from-literal=key=value -n <namespace>
```

**Liveness probe too aggressive:**
Edit the deployment to add `initialDelaySeconds: 30` or increase `failureThreshold`.

**OOMKilled:**
```bash
kubectl patch deployment <name> -n <namespace> \
  -p '{"spec":{"template":{"spec":{"containers":[{"name":"<container>","resources":{"limits":{"memory":"512Mi"}}}]}}}}'
```

## Prevention
- Always set `resources.requests` and `resources.limits` for memory.
- Use `kubectl rollout status` to monitor deployments.
- Configure liveness probes with adequate `initialDelaySeconds`.
- Use Kubernetes Events (`kubectl get events -n <ns> --sort-by='.lastTimestamp'`) for early warning.
