# AWS Deployment — Refresh Agent (Plan 2 of 2: deployment)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.
>
> ⚠️ **This plan creates real, billable AWS resources and runs real LLM/scrape jobs.** Phases C–D should be executed **inline with a human checkpoint before each resource-creating command** — NOT dispatched to autonomous subagents. Phases A–B (code + local container) are safe for normal TDD execution.

**Goal:** Package the LangGraph refresh agent as a Docker image and deploy it to AWS ECS Fargate, triggered once daily by EventBridge Scheduler, at ~$1–2/month.

**Architecture:** A `linux/amd64` Docker image (Python 3.12 + Chromium) running `python -m agent.refresh` → pushed to ECR → run as a Fargate task in a **public subnet with a public IP and no NAT Gateway** → secrets injected from **SSM Parameter Store** → scheduled daily by **EventBridge Scheduler**. MongoDB Atlas is reached over the public internet (Atlas network access `0.0.0.0/0` + strong creds + TLS). Traces go to LangSmith; container logs go to CloudWatch.

**Tech Stack:** Docker + buildx, AWS CLI v2 (region `us-east-1`), ECR, ECS Fargate, IAM, SSM Parameter Store, CloudWatch Logs, EventBridge Scheduler. Builds on the agent code merged in Plan 1.

**Spec:** `docs/superpowers/specs/2026-06-11-food-rescue-agent-rebuild-design.md` §9 (deployment).

**Settled decisions (from the clarification round):** AWS account + CLI + Docker all ready · raw AWS CLI (no Terraform/CDK) · SSM Parameter Store SecureString for secrets · Atlas `0.0.0.0/0` + strong creds · region `us-east-1` · base image `python:3.12-slim` · build `linux/amd64`.

---

## Prerequisites (verify BEFORE Phase C — do not skip)

These are environmental, not tasks. Confirm each:

1. **AWS CLI authenticated** with permissions to create ECR/ECS/IAM/SSM/Logs/Scheduler resources: `aws sts get-caller-identity` returns your account.
2. **Docker with buildx** available: `docker buildx version` succeeds. (Apple Silicon must cross-build `linux/amd64`.)
3. **Atlas reachable and configured:** the cluster is running, Network Access has a `0.0.0.0/0` entry, and a DB user with a strong password exists. The `MONGO_URI` (SRV string with that user) connects from your laptop: `python -c "import pymongo,os;pymongo.MongoClient(os.environ['MONGO_URI']).admin.command('ping')"` → no error. **Note:** Atlas connectivity was previously broken in this project — this must be resolved first or the deployed job cannot write data.
4. **Real API keys** on hand: `GEMINI_API_KEY` (with access to `gemini-2.0-flash-lite`, `gemini-2.0-flash`, `gemini-2.5-flash`) and `LANGCHAIN_API_KEY` (LangSmith, free tier OK).
5. **Agent code present:** `backend_ml/agent/` exists on this branch (merged from Plan 1). `ls backend_ml/agent/cli.py` succeeds.

**Conventions:** Code/Docker work runs in this worktree (`feature/aws-deployment`). Shell variables set in one task do NOT persist to the next task's tool call — re-export the capture block (`ACCOUNT_ID`, `REGION`, etc.) at the top of any task that needs them. Commit code/docs changes; AWS CLI steps create cloud state (not git) — record created ARNs/names in the runbook (Task 12).

---

## File Structure

**Created:**
- `backend_ml/Dockerfile` — image definition (Python 3.12 + Chromium + agent)
- `backend_ml/.dockerignore` — keep the build context small (exclude venv, tests, caches)
- `deploy/task-definition.json` — ECS Fargate task definition (templated; account-specific ARNs filled at registration)
- `deploy/ecs-task-execution-trust.json` — IAM trust policy for the execution role
- `deploy/ecs-scheduler-trust.json` — IAM trust policy for the EventBridge Scheduler role
- `deploy/ssm-secrets-policy.json` — inline policy granting the execution role read on the 3 SSM params
- `deploy/scheduler-runtask-policy.json` — inline policy letting the scheduler RunTask + PassRole
- `docs/deploy-refresh-agent.md` — the runbook (all commands, created-resource inventory, teardown, cost)

**Modified:**
- `backend_ml/agent/config.py` — make select knobs env-overridable
- `docs/decisions.md` — append ADR-019

---

## Phase A — Runtime config (code, TDD)

### Task 1: Make select config knobs env-overridable

**Why:** A first production run should be limitable (e.g. 2 sources) without rebuilding the image, and the task definition should be able to tune cadence/budget per environment. We expose three knobs as env overrides while keeping the current values as defaults.

**Files:**
- Modify: `backend_ml/agent/config.py`
- Test: `backend_ml/tests/agent/test_config_env.py`

- [ ] **Step 1: Write the failing test.**

```python
# backend_ml/tests/agent/test_config_env.py
import importlib


def _reload_config(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import agent.config as cfg
    return importlib.reload(cfg)


def test_defaults_when_no_env(monkeypatch):
    for k in ("REFRESH_MAX_SOURCES", "REFRESH_MAX_COST_USD", "REFRESH_FRESHNESS_HOURS"):
        monkeypatch.delenv(k, raising=False)
    cfg = _reload_config(monkeypatch)
    assert cfg.MAX_SOURCES_PER_RUN == 25
    assert cfg.MAX_COST_USD == 0.50
    assert cfg.FRESHNESS_FLOOR_HOURS == 24


def test_env_overrides_apply(monkeypatch):
    cfg = _reload_config(
        monkeypatch,
        REFRESH_MAX_SOURCES="2",
        REFRESH_MAX_COST_USD="0.05",
        REFRESH_FRESHNESS_HOURS="0",
    )
    assert cfg.MAX_SOURCES_PER_RUN == 2
    assert cfg.MAX_COST_USD == 0.05
    assert cfg.FRESHNESS_FLOOR_HOURS == 0


def test_invalid_env_falls_back_to_default(monkeypatch):
    cfg = _reload_config(monkeypatch, REFRESH_MAX_SOURCES="not-a-number")
    assert cfg.MAX_SOURCES_PER_RUN == 25
```

- [ ] **Step 2: Run to verify it fails.**

Run: `cd backend_ml && ./venv/bin/python -m pytest tests/agent/test_config_env.py -v`
Expected: FAIL (`REFRESH_MAX_SOURCES` not read; constants are hardcoded).

- [ ] **Step 3: Edit `config.py`** — add env helpers at the top (after `import os`) and route the three constants through them. Replace the three bare assignments:

```python
def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


FRESHNESS_FLOOR_HOURS: int = _env_int("REFRESH_FRESHNESS_HOURS", 24)
MAX_SOURCES_PER_RUN: int = _env_int("REFRESH_MAX_SOURCES", 25)
MAX_COST_USD: float = _env_float("REFRESH_MAX_COST_USD", 0.50)
```

Leave `MAX_CONCURRENT`, `CONFIDENCE_THRESHOLD`, `MAX_RETRIES`, `QUARANTINE_THRESHOLD` as hardcoded constants (not runtime-tuned).

- [ ] **Step 4: Run to verify it passes.**

Run: `cd backend_ml && ./venv/bin/python -m pytest tests/agent/test_config_env.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Full agent suite regression.**

Run: `cd backend_ml && ./venv/bin/python -m pytest tests/agent/ -q`
Expected: all agent tests still pass (the `monkeypatch`+`importlib.reload` test must not leak env into others — confirm green).

- [ ] **Step 6: Commit.**

```bash
git add backend_ml/agent/config.py backend_ml/tests/agent/test_config_env.py
git commit -m "feat(agent): make max-sources/budget/freshness env-overridable"
```

---

## Phase B — Container (code + local verification)

### Task 2: Dockerfile + .dockerignore

**Files:**
- Create: `backend_ml/Dockerfile`
- Create: `backend_ml/.dockerignore`

- [ ] **Step 1: Write `.dockerignore`** (keep context small; never ship the venv/secrets/caches).

```
venv/
.venv/
__pycache__/
*.pyc
.pytest_cache/
tests/
.env
.env.*
scripts/.scrape_cache.json
*.md
```

- [ ] **Step 2: Write `Dockerfile`.** Chromium is installed via Playwright with `--with-deps` (pulls the OS libraries Crawl4AI's headless browser needs).

```dockerfile
# backend_ml/Dockerfile
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# System deps needed for the Playwright/Chromium install step
RUN apt-get update && apt-get install -y --no-install-recommends \
        wget gnupg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Chromium + its OS dependencies for Crawl4AI
RUN python -m playwright install --with-deps chromium

# Copy application code (tests/venv excluded via .dockerignore)
COPY . .

# Run the refresh job
CMD ["python", "-m", "agent.refresh"]
```

- [ ] **Step 3: Verify the Dockerfile is syntactically buildable (lint).**

Run: `cd backend_ml && docker build --check . 2>&1 | tail -20` (or proceed to Task 3's real build).
Expected: no Dockerfile syntax errors reported.

- [ ] **Step 4: Commit.**

```bash
git add backend_ml/Dockerfile backend_ml/.dockerignore
git commit -m "build: add Dockerfile (py3.12 + chromium) and .dockerignore for refresh agent"
```

---

### Task 3: Build for linux/amd64 and run the container locally (parity check)

**Why:** We tested the code on Python 3.14; the image is 3.12 + Chromium. This task proves the full pipeline (Crawl4AI/Chromium → Gemini structured output → Mongo write) runs **inside the image** before we touch AWS. Run it against a local Mongo (or your Atlas test DB) with a tiny budget.

**Files:** none (verification only).

- [ ] **Step 1: Build for the Fargate architecture (amd64).**

Run:
```bash
cd backend_ml
docker buildx build --platform linux/amd64 -t equitable-refresh:local --load .
```
Expected: build succeeds; final image present in `docker images | grep equitable-refresh`.

- [ ] **Step 2: Run the container once against a reachable Mongo, limited to 2 sources and a tiny budget.** Provide real keys via env. (Use your Atlas test DB or a local Mongo seeded with ≥1 stale pantry that has a `source_url`.)

Run:
```bash
docker run --rm --platform linux/amd64 \
  -e MONGO_URI="$MONGO_URI" \
  -e DATABASE_NAME="equitable_test" \
  -e GEMINI_API_KEY="$GEMINI_API_KEY" \
  -e LANGCHAIN_API_KEY="$LANGCHAIN_API_KEY" \
  -e LANGCHAIN_TRACING_V2="true" \
  -e LANGCHAIN_PROJECT="equitable-refresh-agent" \
  -e REFRESH_MAX_SOURCES="2" \
  -e REFRESH_MAX_COST_USD="0.05" \
  -e REFRESH_FRESHNESS_HOURS="0" \
  equitable-refresh:local
```
Expected: the process runs to completion and logs a `refresh_summary` / `Refresh complete` line; no Chromium launch errors; exit code 0. If the DB has no stale candidates, the run completes with 0 processed (still a valid pass — it proves the image boots and connects). Seed a stale candidate if you want to see an end-to-end extraction.

- [ ] **Step 3: Confirm observability.** Check the LangSmith project `equitable-refresh-agent` shows a new trace tree for this run. (If `LANGCHAIN_API_KEY` was set, traces should appear.)

- [ ] **Step 4: No commit** (verification only). If the build or run failed, STOP and fix the Dockerfile before continuing — do not proceed to AWS with a broken image.

---

## Phase C — AWS infrastructure (raw AWS CLI) — INLINE, with checkpoints

> Execute these with a human confirming before each resource-creating command. Record every created resource name/ARN in the runbook (Task 12).

### Task 4: ECR repository + push image

**Files:** none (cloud state).

- [ ] **Step 1: Capture identity/region and push target.**

```bash
export REGION=us-east-1
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export ECR_REPO="equitable-refresh"
export IMAGE_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO}:latest"
echo "Pushing to: $IMAGE_URI"
```

- [ ] **Step 2: Create the ECR repo (idempotent).**

```bash
aws ecr describe-repositories --repository-names "$ECR_REPO" --region "$REGION" >/dev/null 2>&1 \
  || aws ecr create-repository --repository-name "$ECR_REPO" --region "$REGION"
```
Expected: repo exists.

- [ ] **Step 3: Authenticate Docker to ECR.**

```bash
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
```
Expected: `Login Succeeded`.

- [ ] **Step 4: Tag + push the amd64 image built in Task 3.**

```bash
docker tag equitable-refresh:local "$IMAGE_URI"
docker push "$IMAGE_URI"
```
Expected: push completes; `aws ecr describe-images --repository-name "$ECR_REPO" --region "$REGION"` lists the `latest` tag.

---

### Task 5: CloudWatch log group + SSM SecureString secrets

**Files:** none (cloud state).

- [ ] **Step 1: Create the log group (idempotent).**

```bash
aws logs create-log-group --log-group-name /ecs/equitable-refresh-agent --region "$REGION" 2>/dev/null || true
aws logs put-retention-policy --log-group-name /ecs/equitable-refresh-agent --retention-in-days 30 --region "$REGION"
```

- [ ] **Step 2: Store the three secrets as SecureString params.** Run with the real values in your shell env (do NOT hardcode in the plan/history; prefer `read -s`).

```bash
aws ssm put-parameter --name /equitable/refresh/MONGO_URI       --type SecureString --value "$MONGO_URI"       --overwrite --region "$REGION"
aws ssm put-parameter --name /equitable/refresh/GEMINI_API_KEY  --type SecureString --value "$GEMINI_API_KEY"  --overwrite --region "$REGION"
aws ssm put-parameter --name /equitable/refresh/LANGCHAIN_API_KEY --type SecureString --value "$LANGCHAIN_API_KEY" --overwrite --region "$REGION"
```
Expected: three params created. Verify: `aws ssm get-parameters-by-path --path /equitable/refresh --region "$REGION" --query "Parameters[].Name"`.

---

### Task 6: IAM roles (execution role, task role, scheduler role)

**Files:**
- Create: `deploy/ecs-task-execution-trust.json`, `deploy/ssm-secrets-policy.json`, `deploy/ecs-scheduler-trust.json`, `deploy/scheduler-runtask-policy.json`

- [ ] **Step 1: Write the trust + inline policy files.**

`deploy/ecs-task-execution-trust.json`:
```json
{ "Version": "2012-10-17", "Statement": [
  { "Effect": "Allow", "Principal": { "Service": "ecs-tasks.amazonaws.com" }, "Action": "sts:AssumeRole" } ] }
```

`deploy/ssm-secrets-policy.json` (replace `REGION`/`ACCOUNT_ID` at apply time with `envsubst` or `sed`):
```json
{ "Version": "2012-10-17", "Statement": [
  { "Effect": "Allow", "Action": ["ssm:GetParameters"],
    "Resource": "arn:aws:ssm:REGION:ACCOUNT_ID:parameter/equitable/refresh/*" },
  { "Effect": "Allow", "Action": ["kms:Decrypt"],
    "Resource": "arn:aws:kms:REGION:ACCOUNT_ID:key/*",
    "Condition": { "StringEquals": { "kms:ViaService": "ssm.REGION.amazonaws.com" } } } ] }
```

`deploy/ecs-scheduler-trust.json`:
```json
{ "Version": "2012-10-17", "Statement": [
  { "Effect": "Allow", "Principal": { "Service": "scheduler.amazonaws.com" }, "Action": "sts:AssumeRole" } ] }
```

`deploy/scheduler-runtask-policy.json` (ARNs filled at apply time):
```json
{ "Version": "2012-10-17", "Statement": [
  { "Effect": "Allow", "Action": ["ecs:RunTask"], "Resource": "*",
    "Condition": { "ArnLike": { "ecs:cluster": "arn:aws:ecs:REGION:ACCOUNT_ID:cluster/equitable-refresh" } } },
  { "Effect": "Allow", "Action": ["iam:PassRole"], "Resource": [
      "arn:aws:iam::ACCOUNT_ID:role/equitableRefreshExecutionRole",
      "arn:aws:iam::ACCOUNT_ID:role/equitableRefreshTaskRole" ] } ] }
```

- [ ] **Step 2: Create the execution role** (ECR pull + logs via managed policy; SSM read via inline).

```bash
aws iam create-role --role-name equitableRefreshExecutionRole \
  --assume-role-policy-document file://deploy/ecs-task-execution-trust.json
aws iam attach-role-policy --role-name equitableRefreshExecutionRole \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
sed "s/REGION/${REGION}/g; s/ACCOUNT_ID/${ACCOUNT_ID}/g" deploy/ssm-secrets-policy.json > /tmp/ssm-secrets-policy.json
aws iam put-role-policy --role-name equitableRefreshExecutionRole \
  --policy-name equitableRefreshSsmRead --policy-document file:///tmp/ssm-secrets-policy.json
```

- [ ] **Step 3: Create a minimal task role** (the app makes no AWS API calls; trust only).

```bash
aws iam create-role --role-name equitableRefreshTaskRole \
  --assume-role-policy-document file://deploy/ecs-task-execution-trust.json
```

- [ ] **Step 4: Create the scheduler role.**

```bash
aws iam create-role --role-name equitableRefreshSchedulerRole \
  --assume-role-policy-document file://deploy/ecs-scheduler-trust.json
sed "s/REGION/${REGION}/g; s/ACCOUNT_ID/${ACCOUNT_ID}/g" deploy/scheduler-runtask-policy.json > /tmp/scheduler-runtask-policy.json
aws iam put-role-policy --role-name equitableRefreshSchedulerRole \
  --policy-name equitableRefreshRunTask --policy-document file:///tmp/scheduler-runtask-policy.json
```

- [ ] **Step 5: Commit the policy files.**

```bash
git add deploy/*.json
git commit -m "deploy: IAM trust + inline policy documents for refresh agent"
```

---

### Task 7: ECS cluster + task definition

**Files:**
- Create: `deploy/task-definition.json`

- [ ] **Step 1: Create the Fargate cluster (idempotent).**

```bash
aws ecs create-cluster --cluster-name equitable-refresh --region "$REGION" 2>/dev/null || true
```

- [ ] **Step 2: Write `deploy/task-definition.json`** (placeholders filled at registration). `secrets` pull from SSM; non-secret config via `environment`.

```json
{
  "family": "equitable-refresh-agent",
  "requiresCompatibilities": ["FARGATE"],
  "networkMode": "awsvpc",
  "cpu": "2048",
  "memory": "4096",
  "executionRoleArn": "arn:aws:iam::ACCOUNT_ID:role/equitableRefreshExecutionRole",
  "taskRoleArn": "arn:aws:iam::ACCOUNT_ID:role/equitableRefreshTaskRole",
  "containerDefinitions": [
    {
      "name": "refresh",
      "image": "ACCOUNT_ID.dkr.ecr.REGION.amazonaws.com/equitable-refresh:latest",
      "essential": true,
      "environment": [
        { "name": "DATABASE_NAME", "value": "equitable" },
        { "name": "LANGCHAIN_TRACING_V2", "value": "true" },
        { "name": "LANGCHAIN_PROJECT", "value": "equitable-refresh-agent" }
      ],
      "secrets": [
        { "name": "MONGO_URI",        "valueFrom": "arn:aws:ssm:REGION:ACCOUNT_ID:parameter/equitable/refresh/MONGO_URI" },
        { "name": "GEMINI_API_KEY",   "valueFrom": "arn:aws:ssm:REGION:ACCOUNT_ID:parameter/equitable/refresh/GEMINI_API_KEY" },
        { "name": "LANGCHAIN_API_KEY","valueFrom": "arn:aws:ssm:REGION:ACCOUNT_ID:parameter/equitable/refresh/LANGCHAIN_API_KEY" }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/equitable-refresh-agent",
          "awslogs-region": "REGION",
          "awslogs-stream-prefix": "refresh"
        }
      }
    }
  ]
}
```

- [ ] **Step 3: Register the task definition** (fill placeholders, register).

```bash
sed "s/REGION/${REGION}/g; s/ACCOUNT_ID/${ACCOUNT_ID}/g" deploy/task-definition.json > /tmp/task-def.json
aws ecs register-task-definition --cli-input-json file:///tmp/task-def.json --region "$REGION"
```
Expected: returns a task definition ARN with `:1` revision. Capture it.

- [ ] **Step 4: Commit the template.**

```bash
git add deploy/task-definition.json
git commit -m "deploy: ECS Fargate task definition for refresh agent (SSM secrets, awslogs)"
```

---

### Task 8: One-off verification run (`aws ecs run-task`)

**Files:** none (cloud state). This is the real end-to-end AWS smoke test, limited to 2 sources.

- [ ] **Step 1: Pick a default-VPC public subnet + a security group.**

```bash
export VPC_ID=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true \
  --query "Vpcs[0].VpcId" --output text --region "$REGION")
export SUBNET_ID=$(aws ec2 describe-subnets --filters Name=vpc-id,Values=$VPC_ID Name=map-public-ip-on-launch,Values=true \
  --query "Subnets[0].SubnetId" --output text --region "$REGION")
export SG_ID=$(aws ec2 describe-security-groups --filters Name=vpc-id,Values=$VPC_ID Name=group-name,Values=default \
  --query "SecurityGroups[0].GroupId" --output text --region "$REGION")
echo "subnet=$SUBNET_ID sg=$SG_ID"
```
(The default SG allows all outbound, which is all the task needs. If `SUBNET_ID` is empty, list subnets and pick a public one manually.)

- [ ] **Step 2: Run the task once with `assignPublicIp=ENABLED` and a 2-source override.**

```bash
aws ecs run-task \
  --cluster equitable-refresh \
  --task-definition equitable-refresh-agent \
  --launch-type FARGATE \
  --region "$REGION" \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_ID],securityGroups=[$SG_ID],assignPublicIp=ENABLED}" \
  --overrides '{"containerOverrides":[{"name":"refresh","environment":[{"name":"REFRESH_MAX_SOURCES","value":"2"},{"name":"REFRESH_MAX_COST_USD","value":"0.05"}]}]}' \
  --query "tasks[0].taskArn" --output text
```
Expected: returns a task ARN. Capture it as `TASK_ARN`.

- [ ] **Step 3: Wait for completion and check exit code.**

```bash
aws ecs wait tasks-stopped --cluster equitable-refresh --tasks "$TASK_ARN" --region "$REGION"
aws ecs describe-tasks --cluster equitable-refresh --tasks "$TASK_ARN" --region "$REGION" \
  --query "tasks[0].containers[0].{exitCode:exitCode,reason:reason}"
```
Expected: `exitCode: 0`. A non-zero exit or `reason` mentioning image/secret/network errors → debug before scheduling (see Step 5).

- [ ] **Step 4: Verify outputs.**
  - **Logs:** `aws logs tail /ecs/equitable-refresh-agent --region "$REGION" --since 10m` → shows scrape/extract/`refresh_summary` lines.
  - **LangSmith:** project `equitable-refresh-agent` shows the run's trace tree.
  - **DB:** the targeted pantries' `last_updated`/`scraped_at` advanced and a `source_metrics` doc exists for each processed `source_url`.

- [ ] **Step 5: If it failed, common causes (debug, then re-run Step 2):**
  - `ResourceInitializationError ... unable to pull secrets` → execution role SSM/KMS policy (Task 6 Step 2) or wrong param ARNs.
  - `CannotPullContainerError` → image arch (must be `linux/amd64`) or ECR perms.
  - Mongo timeout → Atlas `0.0.0.0/0` not set, or `MONGO_URI` param wrong.
  - No LangSmith traces → `LANGCHAIN_API_KEY` param empty or `LANGCHAIN_TRACING_V2` not `true`.

---

### Task 9: EventBridge Scheduler daily cron

**Files:** none (cloud state).

- [ ] **Step 1: Create the schedule** targeting ECS RunTask via the scheduler role. `cron(0 8 * * ? *)` = 08:00 UTC daily.

```bash
export EXEC_ROLE_ARN=arn:aws:iam::${ACCOUNT_ID}:role/equitableRefreshExecutionRole
export SCHED_ROLE_ARN=arn:aws:iam::${ACCOUNT_ID}:role/equitableRefreshSchedulerRole
export TASKDEF_ARN=$(aws ecs describe-task-definition --task-definition equitable-refresh-agent \
  --region "$REGION" --query "taskDefinition.taskDefinitionArn" --output text)
export CLUSTER_ARN=$(aws ecs describe-clusters --clusters equitable-refresh \
  --region "$REGION" --query "clusters[0].clusterArn" --output text)

aws scheduler create-schedule \
  --name equitable-refresh-daily \
  --region "$REGION" \
  --schedule-expression "cron(0 8 * * ? *)" \
  --schedule-expression-timezone "UTC" \
  --flexible-time-window '{"Mode":"OFF"}' \
  --target '{
    "Arn":"'"$CLUSTER_ARN"'",
    "RoleArn":"'"$SCHED_ROLE_ARN"'",
    "EcsParameters":{
      "TaskDefinitionArn":"'"$TASKDEF_ARN"'",
      "LaunchType":"FARGATE",
      "NetworkConfiguration":{"awsvpcConfiguration":{"Subnets":["'"$SUBNET_ID"'"],"SecurityGroups":["'"$SG_ID"'"],"AssignPublicIp":"ENABLED"}}
    }
  }'
```
Expected: schedule ARN returned.

- [ ] **Step 2: Trigger once on demand to confirm the schedule's wiring** (optional but recommended): temporarily set the schedule to fire in ~2 minutes, or simply re-run Task 8's `run-task` (already proven) and rely on Step 1's config matching it. Then confirm a scheduled invocation produces a task: after the next fire, `aws ecs list-tasks --cluster equitable-refresh --region "$REGION" --desired-status STOPPED`.

- [ ] **Step 3: Document pause/delete** (in runbook): `aws scheduler update-schedule --name equitable-refresh-daily --state DISABLED ...` to pause; `aws scheduler delete-schedule --name equitable-refresh-daily` to remove.

---

## Phase D — Documentation

### Task 10: ADR-019 + deploy runbook

**Files:**
- Modify: `docs/decisions.md`
- Create: `docs/deploy-refresh-agent.md`

- [ ] **Step 1: Append ADR-019** to `docs/decisions.md` (before the template section), full body:

  **ADR-019: Refresh agent deployment — ECS Fargate + EventBridge, public-subnet (no NAT), SSM secrets, Atlas 0.0.0.0/0.**
  Context: the Plan-1 refresh agent needs a scheduled, cheap home. Decision: Dockerized CLI on ECS Fargate (2 vCPU/4 GB), triggered daily by EventBridge Scheduler; run in a **public subnet with a public IP and no NAT Gateway** (NAT would be ~$32/mo, dwarfing the ~$1–2/mo job); secrets in **SSM Parameter Store SecureString** (free) injected via the task definition; MongoDB Atlas reached over the internet with network access **0.0.0.0/0** + a strong DB user + TLS (the Fargate public IP is dynamic and can't be allowlisted without reintroducing NAT). Consequences: DB is reachable from any IP (mitigated by credentials/TLS; revisit with PrivateLink if the project moves to Atlas M10+). Image must be built `linux/amd64`. Re-evaluation trigger: if daily runs exceed the budget or the security posture needs tightening, add a NAT+Elastic-IP or PrivateLink path.

- [ ] **Step 2: Write `docs/deploy-refresh-agent.md`** — a runbook containing: the prerequisites, the full command sequence from Tasks 4–9 (copy the commands), a **created-resources inventory** (ECR repo, log group, 3 SSM params, 3 IAM roles, ECS cluster, task def, schedule — fill in actual ARNs as created), the **manual run** command (Task 8 Step 2), the **logs/teardown** commands, and the **cost summary** (~$1–2/mo AWS + ~$0.50–1/mo Gemini). Teardown section: delete schedule → deregister task def → delete cluster → delete roles/policies → delete SSM params → delete log group → delete ECR repo (commands explicit).

- [ ] **Step 3: Commit.**

```bash
git add docs/decisions.md docs/deploy-refresh-agent.md
git commit -m "docs: ADR-019 + deploy runbook for the Fargate refresh agent"
```

---

## Self-Review (completed by plan author)

**Spec §9 coverage:** Dockerfile (Task 2) ✓ · ECR (Task 4) ✓ · IAM execution role (Task 6) ✓ · Fargate task def 2vCPU/4GB (Task 7) ✓ · public subnet + assignPublicIp, no NAT (Task 8 networkConfiguration; ADR-019) ✓ · EventBridge daily cron(0 8 * * ? *) (Task 9) ✓ · secrets via SSM (Tasks 5, 7) ✓ · ADR-019 (Task 10) ✓. Cost summary → runbook (Task 10). The clarification-round decisions (raw CLI, SSM, Atlas 0.0.0.0/0, us-east-1, py3.12, amd64) are all reflected.

**Added beyond spec (justified):** env-overridable config (Task 1) — needed for a safe limited first run and per-task tuning without rebuilds; the local container parity run (Task 3) — de-risks the 3.14→3.12 base-image change empirically; the deploy runbook (Task 10) — operational necessity for a one-person project.

**Placeholder scan:** no TBD/TODO. ARNs are intentionally templated with `ACCOUNT_ID`/`REGION` and filled via captured shell vars / `sed` at apply time — every command is concrete.

**Consistency:** role names (`equitableRefreshExecutionRole`, `equitableRefreshTaskRole`, `equitableRefreshSchedulerRole`), the cluster (`equitable-refresh`), the task family (`equitable-refresh-agent`), the log group (`/ecs/equitable-refresh-agent`), the SSM prefix (`/equitable/refresh/*`), and the env var names (`REFRESH_MAX_SOURCES`/`REFRESH_MAX_COST_USD`/`REFRESH_FRESHNESS_HOURS`, matching Task 1) are identical across all tasks.

**Execution caution:** Phases A–B are normal TDD (safe for subagents). Phases C–D create billable cloud resources and run real LLM/scrape jobs — execute inline with a checkpoint before each resource-creating command; never autonomous.
