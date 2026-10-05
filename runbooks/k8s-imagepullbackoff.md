# Runbook: Kubernetes ImagePullBackOff / ErrImagePull

## What it means
Kubernetes cannot pull the container image. `ErrImagePull` is the immediate failure; `ImagePullBackOff` is the retry-with-backoff state that follows.

## Common root causes

1. **Image does not exist** — wrong tag, typo in image name, or image was deleted from registry.
2. **Registry authentication failure** — missing or expired `imagePullSecret`, or wrong credentials.
3. **Private registry not configured** — image is in a private registry but no pull secret is attached to the pod's service account.
4. **Network connectivity** — node cannot reach the registry (firewall, DNS, proxy issues).
5. **Rate limiting** — Docker Hub or other registries apply pull rate limits.
6. **Wrong image architecture** — image built for amd64 but node is arm64 (or vice versa).

## Key signals to look for

```
kubectl describe pod <name>:
  State: Waiting, Reason: ImagePullBackOff (or ErrImagePull)
  Events:
    Failed to pull image "registry/image:tag": ...
    Error response from daemon: pull access denied
    Error response from daemon: manifest unknown
    net/http: request canceled
```

## Diagnosis steps

```bash
# 1. Describe the pod and read the Events section
kubectl describe pod <pod-name> -n <namespace>

# 2. Check the exact image reference in the pod spec
kubectl get pod <pod-name> -n <namespace> -o jsonpath='{.spec.containers[*].image}'

# 3. List pull secrets on the service account
kubectl get serviceaccount default -n <namespace> -o yaml

# 4. Check if an imagePullSecret exists
kubectl get secret -n <namespace> | grep regcred

# 5. Verify the image exists (from a node or local machine)
docker pull registry/image:tag
```

## Fix patterns

**Missing imagePullSecret:**
```bash
# Create the pull secret
kubectl create secret docker-registry regcred \
  --docker-server=<registry-url> \
  --docker-username=<username> \
  --docker-password=<password> \
  -n <namespace>

# Attach it to the service account
kubectl patch serviceaccount default -n <namespace> \
  -p '{"imagePullSecrets": [{"name": "regcred"}]}'
```

**Wrong image tag (image does not exist):**
```bash
# Find available tags (Docker Hub)
# Then update the deployment image
kubectl set image deployment/<name> <container>=registry/image:correct-tag -n <namespace>
```

**Network / DNS issue on node:**
```bash
# Check node connectivity (from a debug pod)
kubectl run debug --image=busybox --rm -it --restart=Never -- nslookup registry.example.com
```

## Prevention
- Always pin image tags (avoid `:latest` in production).
- Use image digests for immutable references.
- Set up registry mirrors to avoid rate limiting.
- Store `imagePullSecrets` as a Kubernetes Secret and rotate them before expiry.
- Use a container image vulnerability scanner in CI.
