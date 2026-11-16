# AWS architecture: DynamoDB + S3

**Status:** Proposal for team review, partly implemented as Terraform in [`infra/`](../infra/README.md). Nothing has been applied, and no AWS resources exist yet. Implemented decisions are marked **[Implemented]** and summarised in §1a; the rest of the proposal stands as written.

## 1. Goals and constraints

- Serve the lexicon (words, phrases, translations, images, audio, confidence) to the app and the translation pipeline with high availability.
- Protect learner data. Users are newcomers and refugees, some of them minors, so a leak could cause real harm.
- Keep all data in Canada (PIPEDA, plus the expectations of our community partners).
- Never present AI-drafted or unreviewed content as verified. Confidence and review status are stored and served as first-class data.

Design rule: **the lexicon is public content, and learner activity is private data.** They live in separate tables and buckets, with separate keys and roles, so the sensitive side can be locked down without slowing content delivery.

## 1a. Decisions since the proposal

| Decision | Choice | Why |
|---|---|---|
| Compute | **ECS Fargate**, 2 tasks across 2 AZs, autoscaling to 4 on CPU | Whisper settles it: a ~460 MB model, ~1.5 s of CPU per clip and ~2 GB of RAM. On Lambda every cold start would reload the model, and API Gateway's ~30 s integration timeout is a hard ceiling. Fargate keeps the model loaded and runs the Docker image we already have. |
| Entry point | **API Gateway HTTP API → VPC Link → internal ALB** | HTTPS, throttling and access logs at the edge; tasks stay in private subnets with no public IPs. |
| Lexicon store | **DynamoDB in AWS, Postgres locally**, chosen by `VOCAB_BACKEND` | Implements §7 step 3. Postgres stays the authoring store. |
| Whisper | Self-hosted in ca-central-1, model **baked into the image** | Answers the residency risk in §5.3 for transcription: audio never leaves our account. Tasks need no internet access. |
| Network | Private subnets only, **no NAT**; VPC endpoints for ECR, S3, CloudWatch Logs and DynamoDB | Matches §5.2. Interface endpoints cost about as much as a NAT gateway, but there's no internet egress at all. |
| Deployment | **GitHub Actions with OIDC**; Terraform applied by the account owner, not CI | See §7a. |
| Uptime monitoring | CloudWatch alarms, an outside-in canary, a dashboard and a budget | Not covered by §5.4 (security monitoring). See §5.5. |

## 2. Overview

```
Expo app ──HTTPS──► CloudFront ──► S3 media bucket (images, reference audio)   [OAC, no public bucket]
    │
    └──HTTPS──► API Gateway ──► Lambda (FastAPI via Mangum) or ECS Fargate (2+ AZs)
                                   ├─► DynamoDB  rwc-content      (lexicon, read-heavy)
                                   ├─► DynamoDB  rwc-progress     (learner data, private)
                                   ├─► DynamoDB  rwc-review-log   (reviewer audit trail)
                                   ├─► S3 learner-audio           (off by default, short retention)
                                   └─► Translation pipeline (ml/), reads rwc-content via VPC endpoint

Authoring: Postgres (backend/) ──export job──► S3 datasets bucket ──loader──► rwc-content
```

**[Implemented]** The path being built first (the media bucket, CloudFront, the private tables and the export job come later):

```
Expo app ──HTTPS──► API Gateway HTTP API (throttled) ──VPC Link──► internal ALB
                                                                      │
                     private subnets, 2 AZs, no internet route        ▼
                                                     ECS Fargate (FastAPI + Whisper)
                                                        ├─► DynamoDB rwc-<env>-content   (gateway endpoint)
                                                        ├─► ECR, CloudWatch Logs         (interface endpoints)
                                                        └─► S3                           (gateway endpoint, image layers)

Authoring: ml/translation/data/*.json ──python -m app.dynamo_load (loader role)──► rwc-<env>-content
```

Regions: **ca-central-1 (Montréal)** primary, **ca-west-1 (Calgary)** replica. Both are in Canada, so DR doesn't break residency.

## 3. DynamoDB

All tables use on-demand capacity, point-in-time recovery (PITR), deletion protection, and a customer-managed KMS key.

### 3.1 `rwc-content` (public lexicon)

Maps from the Postgres tables in `backend/app/db.py`: `vocabulary_words`, `vocabulary_translations`, `vocabulary_media`, `vocabulary_sources`.

| Item | pk | sk | Key attributes |
|---|---|---|---|
| Entry | `ENTRY#<id>` | `META` | `entry_type` (word/phrase), `english`, `rohingya`, `category_id`, `part_of_speech`, `confidence` (omitted when unscored), `confidence_tier`, `needs_review`, `verification_status`, `dataset`, `schema_version` |
| Translation | `ENTRY#<id>` | `TR#<role>#<n>` | `language`, `script`, `text`, `origin`, `verification`, `confidence` |
| Media | `ENTRY#<id>` | `MEDIA#<kind>#<n>` | `s3_key`, `mime_type`, `verified` |
| Source | `ENTRY#<id>` | `SRC#<kind>#<n>` | `title`, `url`, `evidence`, `license` |
| Category | `CATEGORY#<id>` | `META` | `name`, `description`, `word_count` |

- **Get one entry with everything:** a single `Query` on `pk = ENTRY#<id>`.
- **GSI1, browse by category:** `gsi1pk = CATEGORY#<id>`, `gsi1sk = <english>`.
- **GSI2, review queue:** `gsi2pk = STATUS#<verification_status>`, `gsi2sk = <confidence>#<id>`. Reviewers can list the lowest-confidence entries first.
- **Search (`?q=`):** DynamoDB can't do `ILIKE`. For ~100 words, the app should keep the lexicon in memory or offline, which suits low-connectivity users anyway. If it grows past a few thousand entries, add OpenSearch Serverless, or ship the lexicon to the device as a versioned JSON snapshot from S3.
- **Confidence:** a missing `confidence` attribute means "no scored reference translation". Never write 0 or a default. The Postgres schema follows the same rule.

**[Implemented]** in `infra/modules/data`, `backend/app/vocabulary_dynamo.py` and `backend/app/dynamo_load.py`:
- The table is `rwc-<env>-content` (for example `rwc-dev-content`), so environments can share an account. It has on-demand capacity, PITR, deletion protection, a customer-managed KMS key, and GSI1 and GSI2 exactly as above.
- **Only Entry `META` and `CATEGORY` items are written so far.** Translation, Media and Source child items are deferred, because the API doesn't read them yet. Their data is still in `entry_json`.
- `entry_json` holds the full source entry as a **JSON string**, because the API returns it verbatim as `source_entry`.
- **How the API reads:** it scans the whole table into memory and re-scans every `VOCAB_CACHE_TTL_S` (300 s). Category browsing, `?q=` search (a case-insensitive substring match, like Postgres `ILIKE`) and paging run in Python, as the search bullet above recommends for a small lexicon. If DynamoDB fails after a good load, the last copy keeps being served. If it never loaded, the API serves mock data and `/health` reports `data_source: "mock"`, which fails the canary.
- **GSIs:** created but not used by the API yet. They're for the reviewer queue and for when the lexicon outgrows the cache.
- **Loading:** the loader reuses the Postgres seeder's ID and field logic (`app.seed`), so both stores serve identical entries. A test checks this. It reads the JSON datasets directly; the Postgres → S3 export (§7 step 2) is deferred.

### 3.2 `rwc-progress` (private learner data)

**[Not yet built.]** `/api/progress` still returns mock data. This table needs a decision on learner sign-in (§8 Q2) first.

| pk | sk | Attributes |
|---|---|---|
| `LEARNER#<random uuid>` | `WORD#<id>` | `best_score`, `attempts`, `last_practiced` |
| `LEARNER#<random uuid>` | `SCENARIO#<id>` | `completed_at` |
| `LEARNER#<random uuid>` | `PROFILE` | `created_at`, `last_seen`, `consent_version`, `ttl` |

- **No direct identifiers.** The learner ID is a random UUID. No name, email, phone number, address or immigration details are stored. If the Centre needs to link a learner to a person, that mapping stays in the Centre's own system, not in AWS.
- **Retention:** DynamoDB TTL on `PROFILE.ttl` (for example 12 months after `last_seen`) plus a stream-triggered Lambda that deletes the partition. This is the "delete my data" path. A single `Query` + `BatchWriteItem` on one partition keeps it simple.
- Access is only through the API role, scoped with `dynamodb:LeadingKeys` to the caller's own `LEARNER#` partition where possible.

### 3.3 `rwc-review-log` (audit trail)

**[Not yet built.]**

`pk = ENTRY#<id>`, `sk = <ISO timestamp>#<reviewer>`. It records who changed `verification_status`, from what, to what, and why. This table is append-only (IAM denies `UpdateItem` and `DeleteItem`). It is what lets us say an entry was verified by a native speaker, and when.

## 4. S3

Account-wide **Block Public Access** is on. Every bucket has versioning, default SSE-KMS with a bucket key, and a policy that denies non-TLS requests and unencrypted uploads.

| Bucket | Contents | Access | Retention |
|---|---|---|---|
| `rwc-media` | Word images, reference audio | CloudFront only (Origin Access Control). Never public. | Versioned. Cross-region replication to ca-west-1. |
| `rwc-datasets` | Released lexicon JSON snapshots (the files in `ml/translation/data/`) | Pipeline and loader roles | S3 Object Lock (governance mode) on released versions, so a published lexicon can't be silently altered. |
| `rwc-learner-audio` | Pronunciation recordings, only if the team decides to keep them | Presigned PUT from the app (5-minute expiry, size and content-type limits). Read by the scoring role only. | **Expire after 30 days** (lifecycle rule). Amazon Macie scans it. |
| `rwc-logs` | CloudTrail, CloudFront and S3 access logs | Security role, read-only | 1 year, then delete |

Open decision: do we need to store learner audio at all? The safest answer is to **score it and discard it**, storing only the score. The bucket is specified in case we later want recordings to improve Rohingya speech recognition. That use needs explicit, informed consent (see 5.3).

Media objects are referenced by key (`media/<entry_id>/<kind>/<name>`). The `vocabulary_media.location` column holds that key, and the API turns it into a CloudFront URL.

## 5. Privacy and compliance

### 5.1 Data minimisation
- Store only what the product needs: progress scores and completed items.
- Text typed or spoken into `/api/translate` and `/api/transcribe` is **not stored or logged** by default. Application logs must redact request bodies.

### 5.2 Encryption and access control
- Separate customer-managed KMS keys: `content`, `learner-data`, `learner-audio`. Key policies only allow the roles that need each key, and key rotation is on.
- IAM roles per function (API read content, API write progress, loader, reviewer, scoring). No wildcard `*` resources, and no long-lived access keys. Use IAM roles and OIDC for GitHub Actions.
- Reviewer access (community language experts) via Cognito groups. MFA required for anyone who can change `verification_status`.
- DynamoDB and S3 reached through **VPC gateway endpoints** from the compute layer, so traffic doesn't leave the AWS network.

**[Implemented]** IAM roles in `infra/modules/iam` and `infra/modules/monitoring`:

| Role | Trusted by | Can do |
|---|---|---|
| API task execution | `ecs-tasks.amazonaws.com` (same account only) | Pull the API image from its one ECR repo; write to the API's one log group |
| API task (the app) | `ecs-tasks.amazonaws.com` (same account only) | **Read-only** on the lexicon table and its indexes (`GetItem`, `Query`, `Scan`); `kms:Decrypt` on the content key, only via DynamoDB |
| Lexicon loader | People in the account explicitly granted `sts:AssumeRole` on it | `PutItem` and `BatchWriteItem` on the lexicon table; encrypt with the content key via DynamoDB |
| GitHub deploy | GitHub OIDC, **only** jobs in the `production` environment of `alex9r/rwc-rohingya-english-app` | Push to the API's ECR repo; register task definitions; update the API service; pass only the two task roles, only to ECS |
| Canary | `lambda.amazonaws.com` | Write its artifacts bucket and its own logs; publish metrics in the `CloudWatchSynthetics` namespace only |

The only `*` resources are actions AWS doesn't allow to be scoped: `ecr:GetAuthorizationToken`, `ecs:RegisterTaskDefinition`, `ecs:DescribeTaskDefinition`, `s3:ListAllMyBuckets` (Synthetics) and `cloudwatch:PutMetricData`, which is limited by a namespace condition. Each is commented in the code.

Not yet done from this section:
- The `learner-data` and `learner-audio` keys (those tables and buckets don't exist yet).
- Cognito reviewer access.
- An MFA condition on the loader role. That depends on how the account's users are set up.

### 5.3 Consent, residency and third parties
- Consent must work for low-literacy users: spoken and pictorial, in Rohingya as well as English, with a stored `consent_version` per learner. Wording should be reviewed by the Centre, and that review is not something engineering can sign off.
- **Residency risk to resolve:** the stack lists OpenAI Whisper, ElevenLabs and Google/Anthropic/OpenAI models. Sending learner audio or text to those APIs sends it outside Canada and to a third party. Options: send only non-identifying lexicon text, self-host Whisper in ca-central-1, or get explicit consent and a data-processing agreement. This needs a team and Centre decision before any real learner audio goes through the pipeline.
- Review the Centre's obligations (PIPEDA, and provincial rules if they apply) with a privacy lead before launch. This document is a technical design, not legal advice.

### 5.4 Monitoring and incident response
- CloudTrail with S3 and DynamoDB data events, GuardDuty, AWS Config rules (no public buckets, encryption required, PITR enabled), and an alarm on unusual `rwc-progress` read volume.
- Written breach-response plan: who is told, in what order, within what time. Define it before launch.

**[Not yet built]** in Terraform: CloudTrail data events, GuardDuty, AWS Config.

### 5.5 Uptime monitoring **[Implemented]**

In `infra/modules/monitoring`. Every alarm emails through an SNS topic, on both ALARM and OK:

| Alarm | Fires when |
|---|---|
| API 5xx rate | More than 5% of requests return a 5xx over 5 minutes |
| API latency | p95 above 10 s for 15 minutes. This is loose, because transcription is slow. |
| Unhealthy tasks | Any task failing its `/health` check for 2 minutes |
| API down | No healthy tasks (critical) |
| Running tasks | Fewer tasks than the minimum for 5 minutes |
| CPU / memory | Above 80% / 85% for 10 minutes |
| Canary | The outside-in check fails twice in a row |
| Whisper model errors | More than 5 `model_error` results in 5 minutes (a server fault, not bad audio) |
| Transcription stub | Production served any stub transcription, meaning the image was built without Whisper |

- **Canary:** a CloudWatch Synthetics canary calls the public API every 5 minutes. It checks that `/health` returns `status: ok`, `data_source: dynamodb` and `ml.transcribe: real`, and that `/api/categories` is non-empty.
- **App metrics:** the app writes one JSON log line per ML call (`event: ml_request`, with service, status and latency; see `backend/app/observability.py`). Log metric filters turn those lines into the `RWC/API` metrics.
- **No learner input in logs:**
  - App logs record the route template, status and duration only, with no query strings, bodies, transcripts or translations. A test checks this.
  - API Gateway access logs omit source IPs and bodies.
  - Every log line carries a request ID shared by API Gateway and the app.
- **Dashboard and budget:** a dashboard plus a monthly AWS Budget that emails at 80% of actual spend and at 100% forecast.
- **Not monitored yet:** the alarm thresholds are first guesses to tune after real traffic. Log groups use AWS-managed encryption rather than a customer-managed key, kept for 30 days.

## 6. High availability and recovery

- DynamoDB and S3 are multi-AZ by default. `rwc-content` and `rwc-progress` use **global tables** between ca-central-1 and ca-west-1, and `rwc-media` uses cross-region replication.
- Compute runs in 2+ AZs (Lambda is inherently multi-AZ, or Fargate with 2+ tasks behind an ALB).
  - **[Implemented]** Fargate runs at least 2 tasks, one per AZ, and autoscales to 4.
  - ECS replaces any task that fails the ALB health check.
  - A deploy whose new tasks never become healthy is rolled back automatically by the ECS deployment circuit breaker.
  - The app also keeps serving its cached lexicon if DynamoDB fails.
  - **Deferred:** global tables and replication to ca-west-1. Today a regional outage means downtime until a rebuild.
- PITR gives 35-day restore. Test a restore once before launch.
- **Offline-first is the real availability story for these users.** The app should cache the lexicon and media locally and queue progress writes, so a dropped connection doesn't stop a lesson.
- Targets to confirm with the team: RPO of about 1 minute for progress (global tables), RTO under 1 hour for a regional failure.

## 7. Migration path from today's code

1. **Done in this branch:** the Postgres schema now stores entry type, confidence, confidence tier, needs-review, translations, media and sources as structured data. The seeder loads both datasets (78 entries) idempotently.
2. Add an export script that writes the Postgres content to `rwc-datasets` as a versioned JSON snapshot, and a loader that writes it to `rwc-content`.
3. Add a storage adapter in `backend/app/` so the API can read from DynamoDB when configured and Postgres otherwise, and test it against DynamoDB Local.
4. Write the infrastructure as code (Terraform or CDK) in an `infra/` directory, applied to a dev account first.
5. Move images and audio into `rwc-media` and populate `vocabulary_media.location` with keys.

Postgres stays the authoring and development store. Whether production also needs it is open: DynamoDB alone is simpler to operate, but Postgres is better for reviewer queries and reporting.

**[Progress]**
- **Step 1:** done.
- **Step 2:** changed. `python -m app.dynamo_load` writes the JSON datasets straight to DynamoDB, using the same logic as the Postgres seeder. The S3 snapshot with Object Lock is deferred, so **lexicon updates are a manual re-run of the loader.**
- **Step 3:** done, with `VOCAB_BACKEND=postgres|dynamodb`. CI tests it against moto (an in-process DynamoDB), and `docker compose --profile dynamo` runs DynamoDB Local.
- **Step 4:** Terraform is written in `infra/` and checked in CI, but not applied.
- **Step 5:** not started.

## 7a. Deployment **[Implemented, not yet run]**

| Workflow | When | What |
|---|---|---|
| `ci.yml` | Every PR | Lint and tests for the backend and `ml/`, plus a Docker build |
| `infra.yml` | PRs touching `infra/` | `terraform fmt`, `validate`, `tflint`, `checkov`. No AWS access. |
| `deploy.yml` | Merge to `main` (backend or ml changes), or run by hand | After a reviewer approves in the `production` environment, it assumes the deploy role through OIDC, builds the image with Whisper baked in, pushes it to ECR, rolls it out on ECS, waits for the tasks to be healthy, and smoke-tests `/health`. It skips until the account exists. |

- **Terraform applies:** run by the account owner from their own machine, not by CI. A CI role that can apply would need near-admin rights.
- **First apply:** the bootstrap root creates the state bucket and the GitHub OIDC provider, and the environment starts with zero tasks until the first image exists. The full steps are in `infra/README.md`.

## 8. Open questions for the team

1. Do we store learner audio, or score and discard it?
2. How do learners sign in (anonymous device ID, Cognito, or an account issued by the Centre)?
3. Who is the privacy lead who signs off on consent text and retention periods?
4. Will the ML providers be allowed to see learner data, or do we self-host in Canada?
5. Do we need one AWS account per environment? (Recommended: separate dev, staging and prod accounts.)
6. The README tech-stack table still lists Firebase for storage. It should be updated to match this decision.

Added with the Terraform implementation:

7. **Whose AWS account** do we deploy to, and who holds admin access to it?
8. **The API is open** to anyone with the URL until learner sign-in exists (Q2); only API Gateway throttling protects it. HTTP APIs can't attach AWS WAF, so per-IP rate limits would need CloudFront in front or a switch to a REST API.
9. **No custom domain.** The app uses the default `execute-api` URL, which changes if the API is ever recreated.
10. **TLS ends at API Gateway.** Traffic from the VPC Link to the ALB to the tasks is plain HTTP inside the private VPC. Is that acceptable, or do we need end-to-end TLS?
11. **Lexicon sync:** who re-runs the loader when reviewers change the data, and should that become automatic (the export job in §7 step 2)?
12. **Logs** use AWS-managed encryption and 30-day retention, and VPC flow logs and ALB access logs are off to save cost. Acceptable for launch?
13. **When do we build `rwc-progress`**, now that the content side exists?
