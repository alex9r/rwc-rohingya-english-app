# AWS cost plan against the funding request

**Based on the funding proposal:** $3,000 USD in AWS credits and $5,000 CAD in cash for the 8-month project. This document checks the design in [aws-architecture.md](aws-architecture.md) against each credit line.

All AWS figures are in **USD**. They are estimates from AWS list prices for ca-central-1 (Montréal), entered by hand, not quotes. Check them in the [AWS Pricing Calculator](https://calculator.aws) before the application is submitted. The hosting numbers come from [`infra/cost/estimate.py`](../infra/cost/estimate.py); change an assumption there and rerun it.

## AWS credits: $3,000 USD

| Credit line | Allocated | Estimated use (8 months) | Fit |
|---|---:|---:|---|
| SageMaker (GPU/CPU): speech recognition benchmarking and fine-tuning | $1,800 | Set by GPU hours used (see below) | Depends on usage. Needs a hard budget alert. |
| Bedrock: translation model evaluation | $500 | Set by tokens used (see below) | Depends on usage. Needs a budget alert. |
| S3: recordings, transcripts, validated datasets | $150 | about $40 to $50 | Fits, with room to spare |
| Backend hosting, database, API, monitoring | $350 | about $140 (about $220 with WAF) | Fits, **if the API runs on Lambda** |
| Buffer | $200 | none | Unspent unless needed |
| **Total** | **$3,000** | | |

### Backend hosting, database, API and monitoring ($350)

This line covers everything in `infra/` plus the API: DynamoDB, CloudFront, API Gateway, Lambda, the encryption keys and the security monitoring (GuardDuty, AWS Config, CloudTrail; see [security-monitoring.md](security-monitoring.md)). During the project the users are the frontend team and community partners, so "pilot" scale (about 50 people) is the right assumption. It's budgeted for all 8 months, which is cautious.

| Hosting setup (pilot scale) | Monthly | 8 months | vs $350 line |
|---|---:|---:|---|
| Recommended: Lambda, DynamoDB, no production Postgres | $17.44 | $139 | fits |
| Recommended + WAF | $27.44 | $219 | fits |
| Fargate instead of Lambda | $81.14 | $649 | over by $299 |
| Fargate + Postgres in production + WAF | $123.14 | $985 | over by $635 |

**What this means for the design:**
- **Run the API on Lambda, not Fargate.** Fargate costs the same whether or not anyone is using the app, and it alone would exceed this line.
- **Keep Postgres for authoring and local development only.** A production Postgres database would add about $256 over 8 months.
- **Add WAF only if we see abuse.** It still fits if we need it.
- **Second region:** a few dollars a month at this scale. It fits, but it isn't needed for an 8-month test phase.

Monthly breakdown by scale, in case the app is used more widely after the project:

| Item | Pilot (50 learners) | Launch (500 learners) | Growth (5,000 learners) |
|---|---:|---:|---:|
| KMS keys (4) | $4.00 | $4.00 | $4.00 |
| GuardDuty (threat detection) | $5.00 | $5.00 | $5.00 |
| AWS Config (8 rules) | $5.00 | $5.00 | $5.00 |
| KMS key for security logs (replaces Macie, which can't read audio) | $1.00 | $1.00 | $1.00 |
| CloudTrail data events | $1.00 | $1.00 | $1.00 |
| Secrets Manager (2 secrets) | $0.80 | $0.80 | $0.80 |
| DynamoDB requests | $0.01 | $0.12 | $1.22 |
| DynamoDB storage + backups | $0.50 | $0.50 | $0.50 |
| S3 storage + requests | $0.06 | $0.16 | $1.16 |
| CloudFront media delivery | $0.00 | $0.00 | $0.00 |
| API Gateway | $0.06 | $0.55 | $5.50 |
| Lambda (API compute) | $0.00 | $0.00 | $0.80 |
| KMS requests | $0.01 | $0.07 | $0.75 |
| **Total (Lambda option)** | **$17.44** | **$18.21** | **$26.72** |

### S3 ($150)

The proposal stores audio recordings, transcripts and validated datasets here.
- Storage is cheap: about 200 GB kept for all 8 months costs about $40. App images and audio add under $1 a month.
- **Downloads are the cost to watch.** If the university's computers train on this data, every download out of AWS is billed beyond about 100 GB a month across the account. Do training inside SageMaker in the same region, or download each dataset once and keep it on university storage.

**Research recordings have their own bucket.** App recordings (`learner-audio`) still expire after 30 days. The consented Centre recordings the proposal needs for benchmarking and fine-tuning go to a separate `research-audio` bucket:
- Kept for `research_audio_retention_days`, 365 by default. Set it to whatever the consent form promises.
- Its own encryption key, so the SageMaker role can read research audio but never app recordings.
- Only stores recordings with research consent: "evaluate the scorer" or "train or tune a model".
- Fine-tuning jobs take their file list from `app.recordings.training_recordings()`, which includes only speakers who consented to training.
- The delete-on-request command clears both buckets. It refuses to run if the research bucket isn't configured, so it can't leave research copies behind.

### SageMaker ($1,800)

This is the largest line and the easiest to overspend. Approximate guide: at about $1 to $2 an hour for a single-GPU instance, $1,800 buys roughly 900 to 1,800 GPU hours. Larger GPUs cost several times more per hour. Check current ca-central-1 prices and instance availability before planning experiments.

Guardrails that turn the proposal's commitments into settings:
- **Training jobs, not always-on notebooks.** A job stops billing when it finishes. Notebooks and Studio apps bill until someone stops them, so set them to shut down automatically when idle.
- **Managed spot training** for fine-tuning runs, which is usually much cheaper. Checkpoint the runs so an interruption only loses a little work.
- **Run in ca-central-1** so recordings don't leave Canada. If a GPU type is only available elsewhere, train only on data whose consent allows that.
- **Use university GPUs first** for long runs, as the proposal says.
- **Stop unused endpoints.** A deployed inference endpoint bills every hour it's up.

This isn't in `infra/` yet. SageMaker setup depends on how the speech team works, and it needs its own IAM role with read access to the recordings.

### Bedrock ($500)

Bedrock bills per token. Evaluating translation models on our datasets is small: the lexicon is 150 entries, so even many models over many runs uses a modest number of tokens. $500 is likely more than enough; the main risk is an accidental loop or very large batches.
- **Send only lexicon and benchmark data, never learner recordings or text.**
- **Check model availability in ca-central-1.** Some models are offered only through cross-region inference, which can process requests outside Canada. That is acceptable for public lexicon text, but not for learner data.

### Buffer ($200)

Leave this unassigned. If SageMaker runs low, this buffer and the likely S3 and Bedrock surpluses could cover it, as long as the AWS credit terms allow moving money between lines.

## Tracking spend against the lines

- **AWS Budgets:** one budget per line, with alerts at 50%, 80% and 100%. Add a hard alert on SageMaker.
- **Cost allocation tags:**
  - Terraform already tags every resource with `project` and `environment`.
  - Add a `budget_line` tag (`hosting`, `storage`, `sagemaker`, `bedrock`) so each line's spend shows separately in Cost Explorer.
- **A monthly check:** compare actual spend with the per-line allocation divided by 8.
- **Credits:** confirm the expiry date and what they cover. Credits usually don't cover things like domain registration or Marketplace purchases.

## Cash funding: $5,000 CAD (not AWS)

The cash goes to language validation and doesn't pay for any AWS service. It connects to the design in two places:
- **Translation verification ($1,000) and linguistic QA ($750):** reviewer results go into `reviewer_corrections` and the review log, so the record shows who verified each entry and when.
- **Consent translation and documentation ($250):** the translated consent must match how deletion actually works. Deleted recordings in S3 are gone immediately, but database backups keep deleted rows for up to 35 days, so the form should say "deleted within 35 days" (see [aws-architecture.md](aws-architecture.md) 5.4).

## Not covered by either budget

- Third-party AI APIs outside AWS (Whisper API, ElevenLabs), if the team uses them. They also send data outside Canada.
- Apple developer account ($99 a year), Expo/EAS build plans and a domain name.
