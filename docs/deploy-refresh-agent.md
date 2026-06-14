# Deploy Runbook — Food Rescue Refresh Agent (AWS Fargate)

The refresh agent runs as a **scheduled AWS Fargate task**: once daily it re-scrapes stale
pantries (Crawl4AI → free Jina fallback), extracts with Gemini 3, and updates MongoDB Atlas.
Cost ≈ **$1–2/month** AWS + ≈ **$0.50–1/month** Gemini; scraping is $0.

- **Account / region:** `094009462978` / `us-east-1`
- **Image:** `094009462978.dkr.ecr.us-east-1.amazonaws.com/equitable-refresh:latest`
- **Schedule:** `equitable-refresh-daily` — `cron(0 8 * * ? *)` UTC (08:00 UTC daily)
- **Target DB:** Atlas `equitable` (production)

## Created resources (inventory)

| Type | Name / ARN |
|------|-----------|
| ECR repo | `equitable-refresh` |
| SSM SecureStrings | `/equitable/refresh/{MONGO_URI,GEMINI_API_KEY,LANGCHAIN_API_KEY,JINA_API_KEY}` |
| CloudWatch log group | `/ecs/equitable-refresh-agent` (30-day retention) |
| IAM role (execution) | `equitableRefreshExecutionRole` (ECS-exec managed + inline SSM read) |
| IAM role (task) | `equitableRefreshTaskRole` (minimal) |
| IAM role (scheduler) | `equitableRefreshSchedulerRole` (RunTask + PassRole) |
| ECS cluster | `equitable-refresh` |
| Task definition | `equitable-refresh-agent` (2 vCPU / 4 GB, FARGATE, X86_64) |
| EventBridge schedule | `equitable-refresh-daily` |
| Networking | default VPC public subnet + default SG, `assignPublicIp=ENABLED` (no NAT) |

Policy/task-def source files live in `deploy/` (committed). Account ID + ARNs are baked in.

## Runtime config (task-def env; override per-run with `--overrides`)

| Env var | Default | Meaning |
|---------|---------|---------|
| `DATABASE_NAME` | `equitable` | target DB |
| `REFRESH_MAX_SOURCES` | 25 | max pantries refreshed per run |
| `REFRESH_MAX_COST_USD` | 0.50 | per-run Gemini budget |
| `REFRESH_FRESHNESS_HOURS` | 24 | only refresh pantries staler than this |
| `LANGCHAIN_TRACING_V2` / `LANGCHAIN_PROJECT` | true / equitable-refresh-agent | LangSmith |
| `JINA_ENABLED` / `FIRECRAWL_FALLBACK_ENABLED` | true / false | scraper fallbacks ($0 default) |

## Operate

**Run once on demand** (e.g. limited to 2 sources):
```bash
REGION=us-east-1
SUBNET=subnet-00488861fdf439334 ; SG=sg-0a280c2e03f382e99
aws ecs run-task --cluster equitable-refresh --task-definition equitable-refresh-agent \
  --launch-type FARGATE --region $REGION \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET],securityGroups=[$SG],assignPublicIp=ENABLED}" \
  --overrides '{"containerOverrides":[{"name":"refresh","environment":[{"name":"REFRESH_MAX_SOURCES","value":"2"}]}]}'
```

**Watch logs:**
```bash
aws logs tail /ecs/equitable-refresh-agent --region us-east-1 --since 20m --follow
```

**Pause / resume / delete the schedule:**
```bash
# pause
aws scheduler update-schedule --name equitable-refresh-daily --region us-east-1 --state DISABLED \
  --schedule-expression "cron(0 8 * * ? *)" --schedule-expression-timezone UTC \
  --flexible-time-window '{"Mode":"OFF"}' --target "$(aws scheduler get-schedule --name equitable-refresh-daily --region us-east-1 --query Target)"
# (simpler) delete entirely
aws scheduler delete-schedule --name equitable-refresh-daily --region us-east-1
```

**Change the run time:** re-run `create-schedule`/`update-schedule` with a new `cron(...)`.

**Deploy a new image version** (after code changes):
```bash
cd backend_ml
docker buildx build --platform linux/amd64 -t equitable-refresh:local --load .
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 094009462978.dkr.ecr.us-east-1.amazonaws.com
docker tag equitable-refresh:local 094009462978.dkr.ecr.us-east-1.amazonaws.com/equitable-refresh:latest
docker push 094009462978.dkr.ecr.us-east-1.amazonaws.com/equitable-refresh:latest
# scheduled runs pick up :latest automatically; no task-def change needed
```

## Teardown (full, in order)

```bash
REGION=us-east-1
aws scheduler delete-schedule --name equitable-refresh-daily --region $REGION
aws ecs deregister-task-definition --task-definition equitable-refresh-agent:1 --region $REGION   # repeat per revision
aws ecs delete-cluster --cluster equitable-refresh --region $REGION
aws iam delete-role-policy --role-name equitableRefreshExecutionRole --policy-name equitableRefreshSsmRead
aws iam detach-role-policy --role-name equitableRefreshExecutionRole --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
aws iam delete-role --role-name equitableRefreshExecutionRole
aws iam delete-role --role-name equitableRefreshTaskRole
aws iam delete-role-policy --role-name equitableRefreshSchedulerRole --policy-name equitableRefreshRunTask
aws iam delete-role --role-name equitableRefreshSchedulerRole
for p in MONGO_URI GEMINI_API_KEY LANGCHAIN_API_KEY JINA_API_KEY; do aws ssm delete-parameter --name /equitable/refresh/$p --region $REGION; done
aws logs delete-log-group --log-group-name /ecs/equitable-refresh-agent --region $REGION
aws ecr delete-repository --repository-name equitable-refresh --force --region $REGION
```

## Known follow-ups
- **Curator LLM ranker** falls back to deterministic staleness ordering every run (non-blocking; tracked separately). The agent still selects + refreshes correctly.
- **Atlas network access is `0.0.0.0/0`** (Fargate IP is dynamic). Security rests on the DB password + TLS. Tighten via PrivateLink (Atlas M10+) if needed.
- **AWS root credentials** were used for setup; consider switching to a scoped IAM user.
