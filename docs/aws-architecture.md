# AWS architecture: DynamoDB + S3

**Status:** Proposal for team review, partly implemented as Terraform in [`infra/`](../infra/README.md). Nothing has been applied, and no AWS resources exist yet. Implemented decisions are marked **[Implemented]** and summarised in §1a; the rest of the proposal stands as written. Monthly costs are in [aws-cost-estimate.md](aws-cost-estimate.md).
## 1. Goals and constraints

- Serve the lexicon (words, phrases, translations, images, audio, confidence) to the app and the translation pipeline with high availability.
- Protect learner data. Users are newcomers and refugees, some of them minors, so a leak could cause real harm.
- Keep all data in Canada (PIPEDA, plus the expectations of our community partners).
- Never present AI-drafted or unreviewed content as verified. Confidence and review status are stored and served as first-class data.

Design rule: **the lexicon is public content, and learner activity is private data.** They live in separate tables and buckets, with separate keys and roles, so the sensitive side can be locked down without slowing content delivery.

## 1a. Decisions since the proposal

| Decision | Choice | Why |
|---|---|---|
| Compute | **AWS Lambda** running the backend's container image (FastAPI + Whisper) through the AWS Lambda Web Adapter. Replaces ECS Fargate; see "Compute: Lambda instead of Fargate" below. | Cost: the funding proposal's hosting line is $350 for 8 months, and Fargate as designed cost a fixed ~$180–230 a month. Lambda is close to free at pilot scale (~25 learners, starting around month 7). The same image runs locally and on Lambda. |
| Entry point | **API Gateway HTTP API → Lambda `live` alias** | HTTPS, throttling and access logs at the edge. Nothing can reach the function except through API Gateway. |
| Infrastructure layout | **Two Terraform stacks.** The data stack (`infra/*.tf`: keys, buckets, tables, CloudFront, data-access policies) is the source of truth for data. The compute stack (`infra/envs/dev`) looks those resources up by name and never changes them. | Keeps data decisions in one place, with their author. The compute stack only adds the two permissions the API needed (see §5.2). |
| Lexicon store | **DynamoDB in AWS, Postgres locally**, chosen by `VOCAB_BACKEND` | Implements §7 step 3. Postgres stays the authoring store. Reviewers correct content in DynamoDB through the data stack's `reviewer` policy, and the loader is insert-only so it never undoes them. |
| Whisper | Self-hosted in ca-central-1, model **baked into the image** | Answers the residency risk in §5.3 for transcription: audio never leaves our account. The function needs no internet access to load the model. |
| Network | **No VPC.** The function reaches DynamoDB, S3 and CloudWatch on their public AWS endpoints over TLS, authorised by IAM. | A deliberate deviation from §5.2's VPC gateway endpoints: a VPC would bring back NAT or interface-endpoint costs. Traffic still stays inside AWS, is encrypted, and needs the function's IAM role. |
| Deployment | **GitHub Actions with OIDC**; Terraform applied by the account owner, not CI | See §7a. |
| Uptime monitoring | CloudWatch alarms, an outside-in canary, a dashboard and a budget | Not covered by §5.4 (security monitoring). See §5.5. |

### Compute: Lambda instead of Fargate

The first implementation ran the API on ECS Fargate: two always-on tasks (2 vCPU, 4 GB each) behind an internal load balancer, in private subnets with VPC endpoints. It was replaced with Lambda because its fixed cost didn't fit the funding request ([aws-cost-estimate.md](aws-cost-estimate.md) recommends Lambda for the same reason). The Fargate Terraform is in git history at commit `351c6a9` (`infra/modules/network`, `service` and `data`) if traffic ever justifies it.

| | Fargate (removed) | Lambda (now) |
|---|---|---|
| Cost at pilot scale | Fixed, roughly $180–230 a month as configured (tasks, load balancer, VPC endpoints) | Mostly within the free tier; fits the $350 hosting line |
| First request after idle | Always warm | **Cold start:** loading the image and the Whisper model can take 10–30 s or more. The canary's 5-minute check keeps one instance warm, the app should retry, and `provisioned_concurrency` removes cold starts at an hourly cost. |
| Request timeout | 30 s (API Gateway) | 30 s (same) |
| Largest upload | 10 MB | **4 MB.** Lambda accepts a 6 MB request, and binary uploads arrive base64-encoded (a third larger). Short voice clips are well under this. |
| Concurrency | One task serves many requests at once | One request per instance, and each new instance loads its own copy of Whisper. New AWS accounts can be limited to 10 concurrent instances in total. |
| Network | Private subnets, VPC endpoints, no internet route | No VPC: public AWS endpoints over TLS with IAM. No inbound path except API Gateway. |
| Deploy and rollback | ECS deployment circuit breaker rolls back automatically | Each deploy publishes a version and moves the `live` alias; if the smoke test fails, the workflow moves it back |
| Startup | Model loaded before the task takes traffic | Model loads in a background thread (`RWC_WARMUP=background`), because Lambda allows about 10 s for startup; a request that arrives first waits for it |
| Size ceiling | Up to 16 vCPU / 120 GB | Up to 6 vCPU / 10 GB: enough for Whisper small or medium, not large-v3 (research runs use SageMaker) |
| Monitoring | Healthy-host, running-task, CPU and memory alarms | Errors, throttles and duration alarms (§5.5) |

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
Expo app ──HTTPS──► API Gateway HTTP API (throttled) ──► Lambda "live" alias
                                                         (container image: FastAPI + Whisper, Lambda Web Adapter)
                                                            ├─► DynamoDB rwc-<env>-content   (data stack; TLS + IAM, no VPC)
                                                            ├─► S3 learner-audio             (data stack; uploads only)
                                                            └─► CloudWatch Logs              (JSON logs -> metric filters)

Authoring: ml/translation/data/*.json ──python -m app.dynamo_load (loader role, insert-only)──► rwc-<env>-content
Corrections: reviewers ──UpdateItem (data stack's reviewer policy)──► rwc-<env>-content
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
| Confidence result | `ENTRY#<id>` | `CONF#<kind>#<timestamp>` | `kind` (reference/translation/pronunciation), `model`, `model_version`, `score` (omitted when unscored), `direction`, `output_text` |
| Category | `CATEGORY#<id>` | `META` | `name`, `description`, `word_count` |

- **Get one entry with everything:** a single `Query` on `pk = ENTRY#<id>`.
- **GSI1, browse by category:** `gsi1pk = CATEGORY#<id>`, `gsi1sk = <english>`.
- **GSI2, review queue:** `gsi2pk = STATUS#<verification_status>`, `gsi2sk = <confidence>#<id>`. Reviewers can list the lowest-confidence entries first.
- **Search (`?q=`):** DynamoDB can't do `ILIKE`. For ~100 words, the app should keep the lexicon in memory or offline, which suits low-connectivity users anyway. If it grows past a few thousand entries, add OpenSearch Serverless, or ship the lexicon to the device as a versioned JSON snapshot from S3.
- **Confidence:** a missing `confidence` attribute means "no scored reference translation". Never write 0 or a default. The Postgres schema follows the same rule.

**[Implemented]** The table is defined by the data stack (`infra/dynamodb.tf`); the API reads it through `backend/app/vocabulary_dynamo.py` and the loader is `backend/app/dynamo_load.py`:
- The table is `rwc-<env>-content` (for example `rwc-dev-content`). It has on-demand capacity, PITR, deletion protection, a customer-managed KMS key, and the two indexes above as `gsi1-category` and `gsi2-review`. The loader's `--create-table` (DynamoDB Local and tests only) creates the same indexes.
- **Corrections and re-loads:** reviewers correct entries in place (`UpdateItem`, through the data stack's `reviewer` policy). The loader is **insert-only** by default: it adds new entries and leaves existing ones alone, so a re-load never undoes a correction. `--overwrite` replaces existing entries on purpose. Category items are always rewritten, because their word counts are derived.
- **Only Entry `META` and `CATEGORY` items are written so far.** Translation, Media and Source child items are deferred, because the API doesn't read them yet. Their data is still in `entry_json`.
- `entry_json` holds the full source entry as a **JSON string**, because the API returns it verbatim as `source_entry`.
- **How the API reads:** it scans the whole table into memory and re-scans every `VOCAB_CACHE_TTL_S` (300 s). Category browsing, `?q=` search (a case-insensitive substring match, like Postgres `ILIKE`) and paging run in Python, as the search bullet above recommends for a small lexicon. If DynamoDB fails after a good load, the last copy keeps being served. If it never loaded, the API serves mock data and `/health` reports `data_source: "mock"`, which fails the canary.
- **GSIs:** created but not used by the API yet. They're for the reviewer queue and for when the lexicon outgrows the cache.
- **Loading:** the loader reuses the Postgres seeder's ID and field logic (`app.seed`), so both stores serve identical entries. A test checks this. It reads the JSON datasets directly; the Postgres → S3 export (§7 step 2) is deferred.
- **Confidence history:** each pipeline run adds a `CONF#` item instead of overwriting the last one, so we can compare models and see whether scores move after review. Postgres equivalent: `confidence_results`.

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

`pk = ENTRY#<id>`, `sk = <ISO timestamp>#<reviewer>`. It records who changed `verification_status`, from what, to what, and why. It is what lets us say an entry was verified by a native speaker, and when.

**Reviewer corrections** go here too (`action = correction_proposed` or `correction_decided`, with `field`, `previous_value`, `proposed_value`, `decision`, `reason`). A correction is a proposal: accepting it records the decision but doesn't change the entry. Whoever applies the fix and marks the entry verified does that as a separate, deliberate step. Postgres equivalent: `reviewer_corrections`.

**Append-only:** a resource policy on the table denies `UpdateItem`, `DeleteItem` and `BatchWriteItem` to every principal, including admins. IAM can't stop a `PutItem` from overwriting an item, so writers must use `ConditionExpression: attribute_not_exists(pk)`.

## 4. S3

Account-wide **Block Public Access** is on. Every bucket has default SSE-KMS with a bucket key and a policy that denies non-TLS requests and unencrypted uploads. Every bucket except `rwc-learner-audio` is versioned (see 5.4 for why that one isn't).

| Bucket | Contents | Access | Retention |
|---|---|---|---|
| `rwc-media` | Word images, reference audio | CloudFront only (Origin Access Control). Never public. | Versioned. Cross-region replication to ca-west-1. |
| `rwc-datasets` | Released lexicon JSON snapshots (the files in `ml/translation/data/`) | Pipeline and loader roles | S3 Object Lock (governance mode) on released versions, so a published lexicon can't be silently altered. |
| `rwc-learner-audio` | Pronunciation recordings, only if the team decides to keep them | Presigned PUT from the app (5-minute expiry, size and content-type limits). Read by the scoring role only. | **Expire after 30 days** (lifecycle rule). **Not versioned**, so a delete really removes the audio. Not replicated. Every read and write is logged by CloudTrail data events (Macie was planned here, but it can't read audio; see [security-monitoring.md](security-monitoring.md)). |
| `rwc-research-audio` | Consented Centre recordings for benchmarking and fine-tuning speech models | The data holder uploads them. The SageMaker role reads them (own KMS key, no access to `rwc-learner-audio`). | Kept for the length the consent form states (default 365 days). Versioned, with old versions removed after 7 days. Not replicated. Training uses only recordings with `model_training` consent. |
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

**[Implemented]** The data stack (`infra/iam.tf`) defines what each kind of user may do with data: the `api`, `reviewer`, `recording-deleter`, `research-uploader` and `research-reader` policies, and the append-only review log. The compute stack (`infra/modules/iam`, `infra/modules/monitoring`) creates the roles and attaches those policies unchanged:

| Role | Trusted by | Can do |
|---|---|---|
| API (Lambda function) | `lambda.amazonaws.com` (same account only) | The data stack's **`api` policy**, attached as is (read content, write learner progress, upload recordings). Plus an `api-supplement` policy: write its own log group; `dynamodb:Scan` on the content table only (the lexicon cache loads with one scan; the api policy has no Scan); and a **Deny** on the data keys unless DynamoDB or S3 makes the call (see below). |
| Lexicon loader | People in the account explicitly granted `sts:AssumeRole` on it | `PutItem` on the content table (insert-only by default); encrypt with the content key, only via DynamoDB. The data stack has no role that can create content items; reviewers only update them. |
| GitHub deploy | GitHub OIDC, **only** jobs in the `production` environment of `alex9r/rwc-rohingya-english-app` | Push to the API's ECR repo; update the function's code, publish versions and move its `live` alias. No `iam:PassRole`. |
| Canary | `lambda.amazonaws.com` | Write its artifacts bucket and its own logs; publish metrics in the `CloudWatchSynthetics` namespace only |

**Keys only through DynamoDB or S3.** The `api` policy grants `kms:Decrypt` and `kms:GenerateDataKey` on the `content`, `learner-data` and `learner-audio` keys with no condition, so the API's credentials could call KMS directly. If they leaked, someone could decrypt data protected by those keys without going through the table or bucket. The supplement adds an explicit **Deny** on those keys unless `kms:ViaService` is DynamoDB or S3 in the region. In IAM an explicit Deny always beats an Allow, so this narrows the data stack's policy without editing it. Reads and uploads still work, because those services call KMS on the API's behalf. A direct `kms:Decrypt` carries no `kms:ViaService` value, and the "not equals" test is true when the value is missing, so it's refused. The data stack's four keys and their key policies are unchanged.

The only `*` resources are actions AWS doesn't allow to be scoped: `ecr:GetAuthorizationToken`, `s3:ListAllMyBuckets` (Synthetics) and `cloudwatch:PutMetricData`, which is limited by a namespace condition. Each is commented in the code.

Not yet done from this section:
- Cognito reviewer access, and a role for reviewers to assume (the `reviewer` policy exists in the data stack).
- An MFA condition on the loader role. That depends on how the account's users are set up.

### 5.3 Consent, residency and third parties
- Consent must work for low-literacy users: spoken and pictorial, in Rohingya as well as English, with a stored `consent_version` per learner. Wording should be reviewed by the Centre, and that review is not something engineering can sign off.
- **Residency risk to resolve:** the stack lists OpenAI Whisper, ElevenLabs and Google/Anthropic/OpenAI models. Sending learner audio or text to those APIs sends it outside Canada and to a third party. Options: send only non-identifying lexicon text, self-host Whisper in ca-central-1, or get explicit consent and a data-processing agreement. This needs a team and Centre decision before any real learner audio goes through the pipeline.
- Review the Centre's obligations (PIPEDA, and provincial rules if they apply) with a privacy lead before launch. This document is a technical design, not legal advice.

### 5.4 Deleting recordings on request

The consent form promises that recordings are deleted on request ([pronunciation-recording-collection-plan.md](pronunciation-recording-collection-plan.md)). How that works:

1. The speaker asks the Centre. The Centre knows which pseudonym (for example `S007`) is theirs; the team does not.
2. The data holder runs `python -m app.recordings delete-speaker S007` to preview, then again with `--yes`.
3. The script deletes every version of each object in `rwc-learner-audio` and `rwc-research-audio`, then the `recordings` rows, all in one transaction. If the speaker has research recordings and the research bucket isn't configured, it refuses and deletes nothing. If S3 fails part-way, the rows roll back and the command can be rerun.
4. A row in `recording_deletions` (or a `DELETION#<pseudonym>` item in `rwc-review-log`) records the date and count, with no audio, key names or content.

This is a CLI for the data holder, not an API route, because the API has no authentication yet. An HTTP delete would let anyone who guessed a pseudonym remove someone's data.

**Backup caveat, which the consent text must reflect:** deleted data can survive in backups for a while. Postgres backups and DynamoDB point-in-time recovery keep up to 35 days. S3 recordings go immediately: the deletion removes every version, and neither recording bucket is backed up or replicated. The consent form should say "deleted within 35 days" rather than "deleted immediately", unless we turn PITR off for anything holding learner data.

### 5.5 Monitoring and incident response
- CloudTrail with S3 and DynamoDB data events, GuardDuty, AWS Config rules (no public buckets, encryption required, PITR enabled), and an alarm on unusual `rwc-progress` read volume.
- Written breach-response plan: who is told, in what order, within what time. Define it before launch.

**[Implemented, not yet applied]** in [`infra/security/`](../infra/security/main.tf), a separate account-baseline stack applied before the data stack. It covers CloudTrail (data events on recordings and the private tables), GuardDuty, eight AWS Config rules, IAM Access Analyzer, account-wide S3 Block Public Access, and email alarms for tampering and root use. A draft breach-response plan is in [security-monitoring.md](security-monitoring.md); it needs named people and the Centre's sign-off. Changes from the list above: Macie is dropped (it can't read audio), and the `rwc-progress` read-volume alarm waits until that table is built.

### 5.5 Uptime monitoring **[Implemented]**

In `infra/modules/monitoring`. Every alarm emails through an SNS topic, on both ALARM and OK:

| Alarm | Fires when |
|---|---|
| API 5xx rate | More than 5% of requests return a 5xx over 5 minutes |
| API latency | p95 above 10 s for 15 minutes. This is loose, because transcription is slow. |
| Lambda errors | More than 5 failed invocations in 5 minutes (crash, out of memory, init failure, timeout) |
| Lambda throttles | Any request refused because the function hit its concurrency limit |
| Lambda duration | p95 above 80% of the 30 s timeout for 15 minutes (cold starts or slow transcription) |
| Canary | The outside-in check fails twice in a row. This is also the "API completely down" alarm. |
| Whisper model errors | More than 5 `model_error` results in 5 minutes (a server fault, not bad audio) |
| Transcription stub | Production served any stub transcription, meaning the image was built without Whisper |

- **Canary:** a CloudWatch Synthetics canary calls the public API every 5 minutes. It checks that `/health` returns `status: ok`, `data_source: dynamodb`, `ml.transcribe: real` and `ml.pronunciation: real`, and that `/api/categories` is non-empty. Calling every 5 minutes also keeps one Lambda instance warm.
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
  - **[Implemented]** Lambda, which runs across the region's AZs by itself and starts new instances as requests arrive. There are no servers to replace.
  - A deploy whose new version fails the smoke test is rolled back by the deploy workflow, which moves the `live` alias back to the previous version.
  - The app also keeps serving its cached lexicon if DynamoDB fails.
  - **Deferred:** global tables and replication to ca-west-1. Today a regional outage means downtime until a rebuild.
- PITR gives 35-day restore. Test a restore once before launch.
- **Offline-first is the real availability story for these users.** The app should cache the lexicon and media locally and queue progress writes, so a dropped connection doesn't stop a lesson.
- Targets to confirm with the team: RPO of about 1 minute for progress (global tables), RTO under 1 hour for a regional failure.

## 7. Migration path from today's code

1. **Done:** the Postgres schema stores entry type, confidence, confidence tier, needs-review, translations, media and sources as structured data. The seeder loads seven datasets (150 entries, including main's five domain collections) idempotently.
1. **Done:** confidence history (`confidence_results`), reviewer corrections (`reviewer_corrections`), recordings with consent (`recordings`) and a deletion log (`recording_deletions`), plus the delete-on-request command.
1. **Done:** Terraform for KMS, S3, DynamoDB, CloudFront and IAM in `infra/`. Validated, not applied.
2. Add an export script that writes the Postgres content to `rwc-datasets` as a versioned JSON snapshot, and a loader that writes it to `rwc-content`.
3. Add a storage adapter in `backend/app/` so the API can read from DynamoDB when configured and Postgres otherwise, and test it against DynamoDB Local.
4. Apply `infra/` to a dev account once it exists (see `infra/README.md`).
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
| `infra.yml` | PRs touching `infra/` | `terraform fmt`, `validate` (data stack, compute stack and bootstrap), `tflint`, `checkov`. No AWS access. |
| `deploy.yml` | Merge to `main` (backend or ml changes), or run by hand | After a reviewer approves in the `production` environment, it assumes the deploy role through OIDC, builds the image with Whisper baked in, pushes it to ECR, publishes it as a new Lambda version, moves the `live` alias to it and smoke-tests `/health`. If the smoke test fails, it moves the alias back. It skips until the account exists. |

- **Terraform applies:** run by the account owner from their own machine, not by CI. A CI role that can apply would need near-admin rights.
- **Apply order:** bootstrap (state bucket, GitHub OIDC), then the data stack, then the compute stack. The function can't be created before an image exists, so the first compute apply creates only ECR and the roles, the Deploy workflow pushes the image, and a second apply creates the function. The full steps are in `infra/README.md`.

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
10. **No VPC for the function.** It reaches DynamoDB, S3 and CloudWatch on public AWS endpoints over TLS with IAM, instead of §5.2's VPC gateway endpoints. Acceptable, given the cost of NAT or interface endpoints? (With Lambda there's no plain-HTTP hop: API Gateway invokes the function through AWS's own API.)
11. **Lexicon sync:** reviewers now correct content in DynamoDB, and the loader only adds new entries. Who applies accepted corrections from the Postgres review workflow (`reviewer_corrections`) to DynamoDB, and with what tool?
12. **Logs** use AWS-managed encryption and 30-day retention. Acceptable for launch?
13. **When do we build `rwc-progress`**, now that the content side exists?
14. **Cold starts:** is an occasional slow first request acceptable for the pilot, or do we pay for `provisioned_concurrency = 1` (always one warm instance)?
15. **Account concurrency limit:** new AWS accounts can be capped at 10 concurrent Lambda instances. Request an increase before the pilot if the account is new.
