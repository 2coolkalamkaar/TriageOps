# Runbook: Docker Build Failure

## What it means
A `docker build` command failed during the CI/CD pipeline or locally. The image was not built successfully.

## Common root causes

1. **Network failure fetching packages** — `apt-get`, `pip install`, `npm install` failed due to connectivity.
2. **Base image not found** — `FROM` image tag does not exist or registry is down.
3. **Dependency version mismatch** — a pinned package version no longer exists or conflicts.
4. **Build context too large** — slow build or timeout because `.dockerignore` is missing.
5. **Dockerfile syntax error** — invalid instruction or missing required argument.
6. **Insufficient build resources** — out of disk space, memory, or build timeout.
7. **COPY/ADD path not found** — file referenced in COPY does not exist in build context.
8. **Permission error in build** — RUN commands failing due to insufficient permissions.

## Key signals to look for

```
Step <N>/<total>: RUN ...
The command '/bin/sh -c ...' returned a non-zero code: <N>

Error: failed to solve: ...
  → failed to read dockerfile: ...          (syntax error)
  → failed to pull image: ...               (base image missing)
  → process "/bin/sh -c ..." did not complete successfully: exit code: 1

COPY failed: file not found in build context
```

## Diagnosis steps

```bash
# 1. Read the exact failing step and error message carefully
docker build . 2>&1 | tail -30

# 2. Build with no cache to rule out stale layers
docker build --no-cache .

# 3. Build up to the failing step for interactive debugging
docker build --target <stage-before-failure> .
docker run -it <image-id> /bin/sh  # inspect state

# 4. Check .dockerignore is present and correct
cat .dockerignore

# 5. Check build context size
du -sh .

# 6. Verify base image exists
docker pull <base-image>:<tag>

# 7. Check disk space on build host
df -h
```

## Fix patterns

**Network failure during package install:**
```bash
# Add retry logic to package installs in Dockerfile:
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     package1 \
#     && rm -rf /var/lib/apt/lists/*

# Or configure a package cache/mirror
```

**Missing .dockerignore (large context):**
```bash
# Create .dockerignore with:
cat > .dockerignore << 'EOF'
.git
.env
node_modules
__pycache__
*.pyc
.pytest_cache
.venv
dist
build
EOF
```

**COPY file not found — check relative paths:**
```bash
# Ensure the file exists relative to the build context (usually the project root)
ls -la <path-referenced-in-COPY>
```

**Out of disk on build host:**
```bash
docker system prune  # clean up unused images and containers
df -h                # verify space freed
```

## Prevention
- Pin exact versions in package installs to ensure reproducibility.
- Use multi-stage builds to keep final images small.
- Always include a `.dockerignore` file.
- Build images in CI before merging PRs to catch failures early.
- Use `HEALTHCHECK` in Dockerfiles to validate built images.
- Cache `pip install` and `npm install` layers by copying dependency files first.
