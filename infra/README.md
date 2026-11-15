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
