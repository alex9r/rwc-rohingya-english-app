# AWS architecture: DynamoDB + S3

**Status:** Proposal for team review. Nothing described here is deployed, and no AWS resources have been created.

## 1. Goals and constraints

- Serve the lexicon (words, phrases, translations, images, audio, confidence) to the app and the translation pipeline with high availability.
- Protect learner data. Users are newcomers and refugees, some of them minors, so a leak could cause real harm.
- Keep all data in Canada (PIPEDA, plus the expectations of our community partners).
- Never present AI-drafted or unreviewed content as verified. Confidence and review status are stored and served as first-class data.

Design rule: **the lexicon is public content, and learner activity is private data.** They live in separate tables and buckets, with separate keys and roles, so the sensitive side can be locked down without slowing content delivery.

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

### 3.2 `rwc-progress` (private learner data)

| pk | sk | Attributes |
|---|---|---|
| `LEARNER#<random uuid>` | `WORD#<id>` | `best_score`, `attempts`, `last_practiced` |
| `LEARNER#<random uuid>` | `SCENARIO#<id>` | `completed_at` |
| `LEARNER#<random uuid>` | `PROFILE` | `created_at`, `last_seen`, `consent_version`, `ttl` |

- **No direct identifiers.** The learner ID is a random UUID. No name, email, phone number, address or immigration details are stored. If the Centre needs to link a learner to a person, that mapping stays in the Centre's own system, not in AWS.
- **Retention:** DynamoDB TTL on `PROFILE.ttl` (for example 12 months after `last_seen`) plus a stream-triggered Lambda that deletes the partition. This is the "delete my data" path. A single `Query` + `BatchWriteItem` on one partition keeps it simple.
- Access is only through the API role, scoped with `dynamodb:LeadingKeys` to the caller's own `LEARNER#` partition where possible.

### 3.3 `rwc-review-log` (audit trail)

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

### 5.3 Consent, residency and third parties
- Consent must work for low-literacy users: spoken and pictorial, in Rohingya as well as English, with a stored `consent_version` per learner. Wording should be reviewed by the Centre, and that review is not something engineering can sign off.
- **Residency risk to resolve:** the stack lists OpenAI Whisper, ElevenLabs and Google/Anthropic/OpenAI models. Sending learner audio or text to those APIs sends it outside Canada and to a third party. Options: send only non-identifying lexicon text, self-host Whisper in ca-central-1, or get explicit consent and a data-processing agreement. This needs a team and Centre decision before any real learner audio goes through the pipeline.
- Review the Centre's obligations (PIPEDA, and provincial rules if they apply) with a privacy lead before launch. This document is a technical design, not legal advice.

### 5.4 Monitoring and incident response
- CloudTrail with S3 and DynamoDB data events, GuardDuty, AWS Config rules (no public buckets, encryption required, PITR enabled), and an alarm on unusual `rwc-progress` read volume.
- Written breach-response plan: who is told, in what order, within what time. Define it before launch.

## 6. High availability and recovery

- DynamoDB and S3 are multi-AZ by default. `rwc-content` and `rwc-progress` use **global tables** between ca-central-1 and ca-west-1, and `rwc-media` uses cross-region replication.
- Compute runs in 2+ AZs (Lambda is inherently multi-AZ, or Fargate with 2+ tasks behind an ALB).
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

## 8. Open questions for the team

1. Do we store learner audio, or score and discard it?
2. How do learners sign in (anonymous device ID, Cognito, or an account issued by the Centre)?
3. Who is the privacy lead who signs off on consent text and retention periods?
4. Will the ML providers be allowed to see learner data, or do we self-host in Canada?
5. Do we need one AWS account per environment? (Recommended: separate dev, staging and prod accounts.)
6. The README tech-stack table still lists Firebase for storage. It should be updated to match this decision.
