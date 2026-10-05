# Runbook: Kubernetes OOMKilled Pod

## What it means
A pod container was killed by the Linux OOM killer because it exceeded its memory limit. In Kubernetes, this appears as `OOMKilled` in `kubectl describe pod` and `kubectl get pod` output, with exit code 137.

## Common root causes

1. **Memory limit set too low** — `resources.limits.memory` in the pod spec is insufficient for the workload.
2. **Memory leak in the application** — memory usage grows without bound.
3. **Request/limit misconfiguration** — `requests` set to a low value that allows scheduling, but actual usage far exceeds it, hitting the limit.
4. **Sudden traffic spike** — brief memory spike exceeds the limit.
5. **Large file/dataset loaded into memory** — a batch operation or cache warming event.

## Key signals to look for

```
kubectl describe pod <name>:
  State: Terminated, Reason: OOMKilled, Exit Code: 137
  Last State: Terminated, Reason: OOMKilled

kubectl get pod <name>:
  STATUS: OOMKilled

kubectl top pod <name>:
  MEMORY(bytes) close to or exceeding the limit
```

## Diagnosis steps

```bash
# 1. Confirm OOMKilled and get the container name
kubectl describe pod <pod-name> -n <namespace>

# 2. Check recent memory usage metrics
kubectl top pod <pod-name> -n <namespace>
kubectl top pod <pod-name> -n <namespace> --containers

# 3. Check the configured memory limit
kubectl get pod <pod-name> -n <namespace> -o jsonpath='{.spec.containers[*].resources}'

# 4. Get the last logs before the OOM kill
kubectl logs <pod-name> -n <namespace> --previous

# 5. Check memory trends in monitoring (Prometheus/Grafana if available)
# Query: container_memory_working_set_bytes{pod="<pod-name>"}
```

## Fix patterns

**Increase memory limit:**
```bash
# Edit the deployment
kubectl edit deployment <deployment-name> -n <namespace>
# Under resources.limits.memory, increase the value (e.g. "256Mi" → "512Mi")

# Or using kubectl patch:
kubectl patch deployment <name> -n <namespace> --type=json \
  -p='[{"op":"replace","path":"/spec/template/spec/containers/0/resources/limits/memory","value":"512Mi"}]'
```

**Set Vertical Pod Autoscaler (VPA) to auto-tune resources:**
```bash
# If VPA is installed, create a VPA object for the workload
# VPA will recommend or automatically adjust resource requests/limits
```

**Use a Horizontal Pod Autoscaler (HPA) to spread load:**
```bash
kubectl autoscale deployment <name> \
  --min=2 --max=10 --cpu-percent=70 \
  -n <namespace>
```

**Check and fix memory leak (application-level):**
```bash
# Enable heap profiling (language-specific)
# Java: add -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/tmp/dump.hprof
# Python: use memory_profiler, tracemalloc
# Go: use pprof endpoint
```

## Prevention
- Always set both `resources.requests.memory` and `resources.limits.memory`.
- Use Vertical Pod Autoscaler (VPA) in recommendation mode to tune limits.
- Set up Prometheus alerting for `container_memory_working_set_bytes > 0.8 * limit`.
- Load test applications before production to understand realistic memory usage.
- Implement circuit breakers to shed load before OOM conditions are reached.
