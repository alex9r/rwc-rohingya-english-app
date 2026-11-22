# infra: AWS (Terraform)

Everything AWS for the backend, as code. **Nothing here has been applied yet.** The design and its open questions are in [`docs/aws-architecture.md`](../docs/aws-architecture.md); costs against the funding request are in [`docs/aws-cost-estimate.md`](../docs/aws-cost-estimate.md).

```
Expo app ─HTTPS─► API Gateway (HTTP API, throttled) ─► Lambda "live" alias (container image: FastAPI + Whisper)
                                                         └─► DynamoDB content table, S3 (data stack)
CloudWatch alarms + canary + dashboard ─► SNS ─► email            Budget ─► email
```

## Three stacks, applied in this order

| Stack | Directory | Owns | State |
|---|---|---|---|
| 1. Bootstrap | `bootstrap/` | Terraform state bucket, GitHub OIDC login | local, once |
| 2. **Data stack** | `infra/` root (`*.tf`) | KMS keys, S3 buckets, DynamoDB tables, CloudFront, data-access IAM policies. **Source of truth for data; see [its own guide](#data-stack-infra-root) below.** | local (its README) |
| 3. Compute stack | `envs/dev/` + `modules/` | Lambda, API Gateway, IAM roles, ECR, monitoring | S3 (from bootstrap) |

The compute stack never creates or changes data resources. It looks up the data stack's content table, keys and `rwc-<env>-api` policy by name (`envs/dev/data.tf`), so the data stack must be applied first, with the same `environment`.

| Module | What it is |
|---|---|
| `modules/function` | The API as a Lambda function (container image), its `live` alias and log group |
| `modules/api` | API Gateway HTTP API → Lambda, throttling, access logs |
| `modules/iam` | Lambda role (the data stack's `api` policy + a small supplement), loader role, GitHub deploy role |
| `modules/ecr` | Image repository, readable by Lambda |
| `modules/monitoring` | SNS alerts, alarms, log metric filters, canary, dashboard, budget |

### Why Lambda, not Fargate
The first version ran the API on ECS Fargate (two always-on tasks behind a load balancer, in a private VPC). It was replaced because it costs roughly $180–230 a month whether or not anyone uses the app, against a $350 hosting line for 8 months. The tradeoffs (cold starts, 4 MB uploads, no VPC, alias-based rollback) are in `docs/aws-architecture.md` §1a. The Fargate modules are in git history at commit `351c6a9` (`infra/modules/network`, `service`, `data`) if traffic ever justifies them.

### What the compute stack adds on top of the data stack
- **Lambda role** = the data stack's `rwc-<env>-api` policy, attached unchanged, plus `api-supplement`:
  - `dynamodb:Scan` on the content table only (the API caches the whole lexicon with one scan; the api policy allows GetItem/Query but not Scan).
  - A **Deny** on the data keys unless the call comes through DynamoDB or S3 (`kms:ViaService`), so the API's credentials can't call KMS directly. It narrows the api policy without editing it.
- **Loader role** (`rwc-<env>-content-loader`): `PutItem` on the content table. The data stack has no role that can create content items; reviewers (its `reviewer` policy) correct existing ones. The loader is insert-only by default, so it never overwrites a reviewer's correction.

## Checks (no AWS account needed)

CI runs these on every PR that touches `infra/` (`.github/workflows/infra.yml`). Locally:

```bash
cd infra
terraform fmt -check -recursive
for dir in . envs/dev bootstrap; do (cd $dir && terraform init -backend=false && terraform validate); done
tflint --init && tflint --recursive
checkov -d . --config-file .checkov.yaml
```

The data stack's accepted checkov findings are listed in `.checkov.yaml` (with reasons), not in its files. The compute stack's are inline.

## First deployment (account owner, once)

Use your own AWS credentials (IAM Identity Center/SSO), never root or long-lived keys.

1. **Bootstrap**
   ```bash
   cd infra/bootstrap && terraform init && terraform apply
   ```
   Note the outputs `state_bucket` and `github_oidc_provider_arn`. Back up `bootstrap/terraform.tfstate` (it isn't in git).
2. **Data stack:** follow [its guide](#when-the-aws-account-is-ready) (`cd infra && terraform apply -var-file=dev.tfvars`). Use `environment = "dev"`.
3. **ECR and roles only.** The function can't be created until an image exists.
   ```bash
   cd infra/envs/dev
   cp terraform.tfvars.example terraform.tfvars   # set alert_email, github_oidc_provider_arn
   terraform init -backend-config="bucket=<state_bucket>"
   terraform apply -target=module.ecr -target=module.iam
   ```
4. **GitHub setup, then push the first image.** In the repo settings:
   - Create an environment named `production` with a required reviewer.
   - Add repository variables from `terraform output`: `AWS_ROLE_ARN`, `ECR_REPOSITORY`, `LAMBDA_FUNCTION`, `API_URL` (`API_URL` appears after step 5; add it then).
   - Run the **Deploy** workflow (Actions tab, "Run workflow"). It builds with Whisper baked in, pushes the image, and stops with a notice because the function doesn't exist yet.
5. **Full apply** with the pushed image: set `image_tag = "<git SHA from step 4>"` in `terraform.tfvars`, then `terraform apply`. Confirm the SNS subscription email AWS sends to `alert_email`, and add `API_URL` to the repo variables.
6. **Load the lexicon** with the loader role (the API's own role can't write content):
   ```bash
   # assume the role in terraform output loader_role_arn, then from backend/:
   VOCAB_TABLE=<table_name> AWS_REGION=ca-central-1 python -m app.dynamo_load
   ```
7. **Check:** `curl $API_URL/health` shows `"data_source": "dynamodb"`, `"transcribe": "real"` and `"pronunciation": "real"` (the first call may take a while: cold start), the canary turns green in CloudWatch, and the dashboard (output `dashboard_url`) has data.

Expect a round of fixes on the first apply: `validate` and `checkov` can't catch everything (for example the Synthetics runtime version, which AWS retires over time, and the Lambda Web Adapter version in `backend/Dockerfile`).

## Day to day

- **Code changes:** merge to `main` → the Deploy workflow waits for approval → new image → new Lambda version → `live` alias moves to it after the smoke test passes, or back to the previous version if it fails.
- **Infrastructure changes:** edit Terraform, open a PR (CI checks it), then the account owner runs `terraform apply`. CI never applies.
- **Function settings** (environment variables, memory in `envs/dev`): `terraform apply` updates the function, and they reach traffic with the next published version, i.e. the next deploy.
- **Lexicon changes:** re-run step 6. New entries are added; existing ones are left alone, so reviewer corrections survive. `--overwrite` replaces existing entries (and their corrections) on purpose. The app picks changes up within `VOCAB_CACHE_TTL_S` (5 minutes).
- **Cold starts:** the canary's 5-minute check keeps one instance warm. If the first request of the day is still too slow, set `provisioned_concurrency = 1` (billed every hour).
- **Canary script changes** (`modules/monitoring/canary/`): Terraform may not notice a changed zip; taint the canary or bump its runtime to force an update.

## Local DynamoDB

```bash
cd backend
docker compose --profile dynamo up -d dynamodb-local
export DYNAMODB_ENDPOINT_URL=http://localhost:8001 AWS_ACCESS_KEY_ID=local AWS_SECRET_ACCESS_KEY=local AWS_REGION=ca-central-1
python -m app.dynamo_load --create-table   # same indexes as the data stack's content table
VOCAB_BACKEND=dynamodb uvicorn app.main:app   # PYTHONPATH must include the repo root for ml/
```

---

## Data stack (infra/ root)

*The data stack's own guide, kept as its author wrote it (headings moved down one level to fit this page). Compute and API Gateway, listed below as not yet included, are now the compute stack above.*

Terraform for [docs/aws-architecture.md](../docs/aws-architecture.md). **It hasn't been applied anywhere.** It passes `terraform validate` and a Trivy misconfiguration scan (two known gaps, listed below). Monthly costs are in [docs/aws-cost-estimate.md](../docs/aws-cost-estimate.md).

### What it creates

| File | Resources |
|---|---|
| `kms.tf` | Four customer-managed keys with rotation: `content`, `learner-data`, `learner-audio`, `research-audio` |
| `s3.tf` | `media`, `datasets` (Object Lock), `logs`, `learner-audio` (unversioned, expires after 30 days) and `research-audio` (consented Centre recordings, kept 365 days by default). All private, KMS-encrypted and TLS-only. |
| `dynamodb.tf` | `content`, `progress` (TTL) and `review-log`. On-demand, point-in-time recovery, KMS, deletion protection. |
| `cloudfront.tf` | Private media delivery (Origin Access Control). The bucket is never public. |
| `iam.tf` | `api`, `reviewer`, `recording-deleter` (both recording buckets), `research-uploader` and `research-reader` (for SageMaker) policies, plus a table policy that makes `review-log` append-only for everyone |

### When the AWS account is ready

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

### Not yet included

Each of these is described in the architecture doc and deliberately left for later.

- **Compute** (Lambda or Fargate) and **API Gateway**, pending the team's choice.
- **Cognito** for reviewer sign-in, pending the sign-in decision.
- **Second region:** DynamoDB global-table replicas and S3 replication to ca-west-1. Streams are already on. Replicas need a KMS key in ca-west-1.
- **Account-level security:** CloudTrail, GuardDuty, AWS Config and Macie. These belong in an account baseline, not this stack.
- **CloudFront access logs and WAF:** these are the two Trivy findings. Logs need an ACL-enabled log bucket. WAF is optional (see the cost estimate).
- **Remote Terraform state.**
