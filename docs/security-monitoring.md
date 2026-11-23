# Security monitoring and incident response

**Status:** Terraform written in [`infra/security/`](../infra/security/main.tf), validated and checked in CI, **not applied** (no AWS account yet). The response plan below needs names and sign-off from the Centre before launch.

Our users are refugees and newcomers, some of them minors. The data we hold is deliberately thin (random learner IDs, scores, consented voice recordings, no names or contact details), but a voice recording can still identify someone. Monitoring exists to answer three questions quickly: **did anyone reach learner data who shouldn't have, did anything become public, and did anyone switch the protections off?**

## What is watched

| Tool | Watches | Emails when |
|---|---|---|
| **CloudTrail** | Every management API call in the account. Every read and write of a recording (`learner-audio`, `research-audio`) and of the private tables (`progress`, `review-log`). Logs are KMS-encrypted, integrity-checked, and can't be deleted by hand. Kept 1 year. | Never directly. It is the record investigators read. |
| **GuardDuty** | CloudTrail, S3 data events and Lambda network activity, for stolen credentials, unusual data access, and calls from known-bad addresses | A finding of medium severity (4) or higher |
| **AWS Config** (8 rules) | Buckets: not public, TLS only, KMS encryption; account-wide public access block. Tables: point-in-time recovery, KMS. Keys: rotation on. Trail: log validation on. | Any resource becomes non-compliant |
| **IAM Access Analyzer** | Any bucket, key, role or table that can be reached from outside the account | A new external-access finding |
| **Tamper alarm** | Someone stops or edits the trail, turns off GuardDuty or Config, disables or schedules deletion of a key, changes a bucket policy or the public access block, deletes a table or changes its backups | Any of these calls |
| **Root-use alarm** | The root user makes an API call in ca-central-1 | Any use |

All alerts go to one KMS-encrypted SNS topic that emails `security_alert_email`. Uptime alerts (API down, errors, cost) are separate and already exist in `infra/modules/monitoring`.

**Account-wide S3 Block Public Access** is set in this stack too. The architecture doc promised it, but until now only individual buckets had it.

### Deliberately left out

- **Macie.** The architecture doc planned to use it to scan `learner-audio`, but Macie classifies text-type files (documents, CSV, JSON) and can't read audio. Turn it on if the project starts storing transcripts.
- **CloudWatch Logs copy of CloudTrail.** It costs per GB ingested. EventBridge already sees the management events the alarms need.
- **Security Hub** and GuardDuty malware or runtime scanning. They cost money and we run no EC2, EKS or RDS.
- **Public content** (lexicon table, media and datasets buckets) isn't data-event logged. It holds nothing private, and the API reads it constantly.
- **Alarm on unusual `progress` read volume** (architecture §5.5). This waits until the `progress` table is built; GuardDuty's S3 anomaly detection covers recordings until then.

### Cost

Roughly $3–5 a month at pilot scale (GuardDuty's first 30 days are free). The cost estimate budgets $12, so this is cautious. Data-event logging is $0.10 per 100,000 events, and Config is billed per item recorded and per rule evaluation, so cost grows with use, not with time.

## Setting it up

Apply order: **bootstrap → security → data stack → compute stack.** Security goes before the data stack so the first recording bucket is watched from the moment it exists.

```bash
cd infra/security
cp terraform.tfvars.example terraform.tfvars   # same environment and name_prefix as the data stack
terraform init && terraform plan && terraform apply
```

Then:
1. **Confirm the SNS subscription** from the email AWS sends. No alerts arrive until this is done.
2. Turn on **root sign-in alerts** in the account settings. Root console sign-ins are logged in us-east-1, which this stack's region-local alarm doesn't see.
3. Check that the eight Config rules all show *Compliant* once the data stack is applied. A non-compliant result on day one is a real gap.

## Response plan (draft: needs the Centre's names and sign-off)

### Roles to fill before launch

| Role | Does | Who |
|---|---|---|
| **Incident lead** | Reads alerts, runs the first-response steps, decides whether it is an incident | _TBD (technical team member with AWS admin)_ |
| **Privacy lead** | Decides whether a breach is reportable, owns contact with affected people and regulators | _TBD (Centre; architecture §8 Q3)_ |
| **Centre contact** | Knows which pseudonym is which person, contacts affected learners in their language | _TBD_ |
| **Backup** | Covers when the incident lead is unavailable | _TBD_ |

`security_alert_email` should reach the incident lead **and** the backup (use a shared inbox or group), not one person's personal address.

### First response, by alert

| Alert | First check (within 24 hours) | If it's real |
|---|---|---|
| GuardDuty finding | Read the finding: which principal, which resource, from where | If credentials are involved: disable the access key or revoke the role's sessions, then rotate. Preserve logs. |
| Config: bucket public / not encrypted / no TLS | Who changed it? Look up the call in CloudTrail (Event history, filtered by resource). | Revert it with `terraform apply` on the data stack. If a recording bucket was public, treat it as a possible breach. |
| Access Analyzer: external access | Is the sharing intended? (Almost nothing in this project should be.) | Remove the grant, then check CloudTrail data events for reads from outside the account during the exposure window. |
| Tamper alarm | Was it a planned change by a named team member? | If not: assume compromise. Re-enable the control, lock down IAM users and roles, and treat it as a security incident. |
| Root use | Was it the account owner, on purpose? | If not: change the root password, check MFA, and review everything done in the session. |

### If learner data may have been exposed

1. **Contain:** cut off the access path (credentials, policy or grant). Don't delete anything; logs and the affected resources are evidence.
2. **Scope with CloudTrail data events:** which recordings or learner partitions were read, by whom, and when. Data events record every read, so this can be answered precisely.
3. **Tell the privacy lead the same day.** They decide what follows, not engineering.
4. **Assess harm.** Under PIPEDA, a breach that creates a *real risk of significant harm* must be reported to the Office of the Privacy Commissioner and to the affected people as soon as feasible. Every breach must be recorded, reportable or not, and the record kept for 24 months. For this group, a voice recording linked to someone's refugee status could be significant harm; the privacy lead should assume so unless shown otherwise.
5. **Notify affected people through the Centre,** in Rohingya and in a form that works for low-literacy users, the same way consent was collected.
6. **Write up** what happened and what changed, within 2 weeks.

This plan is a technical draft, not legal advice. The Centre's privacy lead should confirm the reporting duties (PIPEDA, plus any provincial rules) and the timelines.

## Open questions

1. Who are the incident lead, privacy lead, Centre contact and backup?
2. Which address should `security_alert_email` be?
3. Is a response within 24 hours realistic for a volunteer or student team? If not, which alerts need a faster path?
4. Should CloudTrail logs be kept longer than 1 year? Longer helps investigations, but it is more data to hold.
