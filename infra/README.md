# infra: AWS deployment (Terraform)

Everything AWS for the backend, as code. **Nothing here has been applied yet.** The design and its open questions are in [`docs/aws-architecture.md`](../docs/aws-architecture.md).

```
Expo app ─HTTPS─► API Gateway (HTTP API, throttled) ─VPC Link─► internal ALB ─► ECS Fargate (2 tasks, 2 AZs, private subnets)
                                                                                 └─► DynamoDB rwc-<env>-content
CloudWatch alarms + canary + dashboard ─► SNS ─► email            Budget ─► email
```

| Directory | What it is |
|---|---|
| `bootstrap/` | One-time setup: Terraform state bucket and GitHub OIDC login. Local state. |
| `envs/dev/` | The dev environment. Wires the modules together. |
| `modules/network` | VPC, two private subnets, VPC endpoints (no NAT, no internet route) |
| `modules/data` | DynamoDB lexicon table + KMS key |
| `modules/ecr` | Image repository |
| `modules/service` | ECS cluster, task definition, service, internal ALB, autoscaling, log group |
| `modules/api` | API Gateway HTTP API, VPC Link, throttling, access logs |
| `modules/iam` | Execution, task, loader and GitHub deploy roles |
| `modules/monitoring` | SNS alerts, alarms, log metric filters, canary, dashboard, budget |

## Checks (no AWS account needed)

CI runs these on every PR that touches `infra/` (`.github/workflows/infra.yml`). Locally:

```bash
cd infra
terraform fmt -check -recursive
(cd envs/dev && terraform init -backend=false && terraform validate)
(cd bootstrap && terraform init -backend=false && terraform validate)
tflint --init && tflint --recursive
checkov -d .
```

## First deployment (account owner, once)

Use your own AWS credentials (IAM Identity Center/SSO), never root or long-lived keys.

1. **Bootstrap**
   ```bash
   cd infra/bootstrap && terraform init && terraform apply
   ```
   Note the outputs `state_bucket` and `github_oidc_provider_arn`. Back up `bootstrap/terraform.tfstate` (it isn't in git).
2. **Apply dev with no tasks.** No image exists yet, so the service starts at zero.
   ```bash
   cd infra/envs/dev
   cp terraform.tfvars.example terraform.tfvars   # set alert_email, github_oidc_provider_arn; desired_count = 0
   terraform init -backend-config="bucket=<state_bucket>"
   terraform apply
   ```
   Confirm the SNS subscription email AWS sends to `alert_email`.
3. **GitHub setup.** In the repo settings:
   - Create an environment named `production` with a required reviewer.
   - Add repository variables from `terraform output`: `AWS_ROLE_ARN`, `ECR_REPOSITORY`, `ECS_CLUSTER`, `ECS_SERVICE`, `ECS_TASK_FAMILY`, `API_URL`.
4. **First image.** Run the **Deploy** workflow (Actions tab, "Run workflow"). It builds with Whisper baked in and pushes to ECR.
5. **Start the service.** Set `desired_count = 2` in `terraform.tfvars` and `terraform apply` again.
6. **Load the lexicon** with the loader role (the API's own role is read-only):
   ```bash
   # assume the role in terraform output loader_role_arn, then from backend/:
   VOCAB_TABLE=<table_name> AWS_REGION=ca-central-1 python -m app.dynamo_load
   ```
7. **Check:** `curl $API_URL/health` shows `"data_source": "dynamodb"` and `"transcribe": "real"`, the canary turns green in CloudWatch, and the dashboard (output `dashboard_url`) has data.

Expect a round of fixes on the first apply: `validate` and `checkov` can't catch everything (for example the Synthetics runtime version, which AWS retires over time).

## Day to day

- **Code changes:** merge to `main` → the Deploy workflow waits for approval → new image → ECS rolls it out, and rolls back automatically if the new tasks never get healthy.
- **Infrastructure changes:** edit Terraform, open a PR (CI checks it), then the account owner runs `terraform apply`. CI never applies.
- **Task environment variables** (in `envs/dev/main.tf`) reach running tasks on the next deploy, not on `terraform apply`.
- **Lexicon changes:** re-run step 6. The app picks them up within `VOCAB_CACHE_TTL_S` (5 minutes).
- **Canary script changes** (`modules/monitoring/canary/`): Terraform may not notice a changed zip; taint the canary or bump its runtime to force an update.

## Local DynamoDB

```bash
cd backend
docker compose --profile dynamo up -d dynamodb-local
export DYNAMODB_ENDPOINT_URL=http://localhost:8001 AWS_ACCESS_KEY_ID=local AWS_SECRET_ACCESS_KEY=local AWS_REGION=ca-central-1
python -m app.dynamo_load --create-table
VOCAB_BACKEND=dynamodb uvicorn app.main:app   # PYTHONPATH must include the repo root for ml/
```
# infra: AWS (Terraform)

Terraform for [docs/aws-architecture.md](../docs/aws-architecture.md). **It hasn't been applied anywhere.** It passes `terraform validate` and a Trivy misconfiguration scan (two known gaps, listed below). Monthly costs are in [docs/aws-cost-estimate.md](../docs/aws-cost-estimate.md).

## What it creates

| File | Resources |
|---|---|
| `kms.tf` | Four customer-managed keys with rotation: `content`, `learner-data`, `learner-audio`, `research-audio` |
| `s3.tf` | `media`, `datasets` (Object Lock), `logs`, `learner-audio` (unversioned, expires after 30 days) and `research-audio` (consented Centre recordings, kept 365 days by default). All private, KMS-encrypted and TLS-only. |
| `dynamodb.tf` | `content`, `progress` (TTL) and `review-log`. On-demand, point-in-time recovery, KMS, deletion protection. |
| `cloudfront.tf` | Private media delivery (Origin Access Control). The bucket is never public. |
| `iam.tf` | `api`, `reviewer`, `recording-deleter` (both recording buckets), `research-uploader` and `research-reader` (for SageMaker) policies, plus a table policy that makes `review-log` append-only for everyone |

## When the AWS account is ready

Prerequisites:
- An AWS account per environment (start with `dev`), owned by the organisation, not a personal account.
- MFA on the root user, then root is never used again.
- An admin user through IAM Identity Center.
- Terraform 1.6 or later, or run it in Docker as shown below.

```bash
cd infra
cp dev.tfvars.example dev.tfvars        # set name_prefix to something globally unique
aws sso login --profile rwc-dev
export AWS_PROFILE=rwc-dev
terraform init
terraform plan  -var-file=dev.tfvars    # read the plan before applying
terraform apply -var-file=dev.tfvars
```

Without a local Terraform install: `docker run --rm -it -v "$PWD":/w -w /w -v ~/.aws:/root/.aws -e AWS_PROFILE hashicorp/terraform:1.9 plan -var-file=dev.tfvars`

State is local by default. Before a second person runs this, add a remote backend: an S3 bucket in ca-central-1 with versioning and encryption, using S3 native locking (`use_lockfile = true`). Don't commit `*.tfstate` or `*.tfvars`; `.gitignore` excludes them.

After applying, attach the `policy_arns` outputs to the API's role. For the deletion command, set `RECORDINGS_BUCKET` to `buckets.learner-audio` and `RESEARCH_RECORDINGS_BUCKET` to `buckets.research-audio`. Attach `research_reader` to the SageMaker execution role once it exists.

## Not yet included

Each of these is described in the architecture doc and deliberately left for later.

- **Compute** (Lambda or Fargate) and **API Gateway**, pending the team's choice.
- **Cognito** for reviewer sign-in, pending the sign-in decision.
- **Second region:** DynamoDB global-table replicas and S3 replication to ca-west-1. Streams are already on. Replicas need a KMS key in ca-west-1.
- **Account-level security:** CloudTrail, GuardDuty, AWS Config and Macie. These belong in an account baseline, not this stack.
- **CloudFront access logs and WAF:** these are the two Trivy findings. Logs need an ACL-enabled log bucket. WAF is optional (see the cost estimate).
- **Remote Terraform state.**
