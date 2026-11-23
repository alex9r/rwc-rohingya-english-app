"""Monthly AWS cost estimate for docs/aws-cost-estimate.md.

Prices are approximate ca-central-1 list prices in USD, entered by hand. Check every
one against https://calculator.aws before putting numbers in a funding application.
Run: python3 infra/cost/estimate.py
"""

PRICE = {
    "ddb_write_per_m": 0.69,  # DynamoDB on-demand, per million write request units
    "ddb_read_per_m": 0.14,  # per million read request units
    "ddb_gb": 0.28,  # storage, per GB-month
    "ddb_pitr_gb": 0.22,  # continuous backups, per GB-month
    "s3_gb": 0.025,  # S3 Standard, per GB-month
    "s3_put_per_k": 0.0055,
    "s3_get_per_k": 0.00044,
    "kms_key": 1.00,  # per customer-managed key per month
    "kms_per_10k": 0.03,
    "cf_gb": 0.085,  # CloudFront, North America, beyond the free allowance
    "cf_free_gb": 1024,  # always-free CloudFront transfer per month
    "apigw_per_m": 1.10,  # HTTP API, per million requests
    "lambda_free_req_m": 1.0,  # always-free Lambda requests per month (millions)
    "lambda_req_per_m": 0.20,
    "lambda_gb_s": 0.0000166667,
    "lambda_free_gb_s": 400_000,
    # Fargate alternative: 2 tasks x 0.5 vCPU / 1 GB, plus an Application Load Balancer.
    "fargate_vcpu_h": 0.04456,
    "fargate_gb_h": 0.004865,
    "alb_h": 0.02475,
    "alb_lcu_month": 6.0,
}

# Fixed monthly costs that don't scale with learners (small-account estimates).
FIXED = {
    "KMS keys (4)": 4 * PRICE["kms_key"],
    "GuardDuty (threat detection)": 5.00,
    "AWS Config (8 rules)": 5.00,
    "KMS security-log key (Macie not used: it can't read audio)": PRICE["kms_key"],
    "CloudTrail data events": 1.00,
    "Secrets Manager (2 secrets)": 0.80,
}

OPTIONAL = {
    "WAF on CloudFront (1 ACL, 5 rules)": 10.00,
    "Fargate instead of Lambda (2 tasks + ALB)": round(
        2 * 730 * (0.5 * PRICE["fargate_vcpu_h"] + 1 * PRICE["fargate_gb_h"])
        + 730 * PRICE["alb_h"] + PRICE["alb_lcu_month"], 2
    ),
    "Keep Postgres in production (RDS t4g.micro, Multi-AZ)": 32.00,
    "Second region: global-table writes + S3 replication": None,  # see note below
}

# Per active learner per month.
USAGE = {
    "api_requests": 1_000,  # ~20 sessions x 50 calls
    "ddb_reads": 1_000,
    "ddb_writes": 150,
    "media_mb": 50,  # lexicon images/audio; cached on the device after first download
    "recordings": 30,  # only if recordings are stored
    "recording_kb": 60,
    "lambda_ms": 120,
    "lambda_mb": 512,
}

SCENARIOS = {"Pilot": 50, "Launch": 500, "Growth": 5_000}
DATA_GB = 1.0  # lexicon + progress tables; tiny for years at this scale


def variable_costs(learners: int) -> dict[str, float]:
    u = {k: v * learners for k, v in USAGE.items()}
    lambda_req_m = u["api_requests"] / 1e6
    gb_s = u["api_requests"] * (USAGE["lambda_ms"] / 1000) * (USAGE["lambda_mb"] / 1024)
    media_gb = u["media_mb"] / 1024
    rec_gb = u["recordings"] * USAGE["recording_kb"] / 1024 / 1024  # 30-day retention
    return {
        "DynamoDB requests": u["ddb_reads"] / 1e6 * PRICE["ddb_read_per_m"]
        + u["ddb_writes"] / 1e6 * PRICE["ddb_write_per_m"],
        "DynamoDB storage + backups": DATA_GB * (PRICE["ddb_gb"] + PRICE["ddb_pitr_gb"]),
        "S3 storage + requests": (2 + rec_gb) * PRICE["s3_gb"]
        + u["recordings"] / 1000 * PRICE["s3_put_per_k"]
        + u["recordings"] / 1000 * PRICE["s3_get_per_k"],
        "CloudFront media delivery": max(0, media_gb - PRICE["cf_free_gb"]) * PRICE["cf_gb"],
        "API Gateway": lambda_req_m * PRICE["apigw_per_m"],
        "Lambda (API compute)": max(0, lambda_req_m - PRICE["lambda_free_req_m"])
        * PRICE["lambda_req_per_m"]
        + max(0, gb_s - PRICE["lambda_free_gb_s"]) * PRICE["lambda_gb_s"],
        "KMS requests": u["api_requests"] * 0.05 / 10_000 * PRICE["kms_per_10k"],
    }


# AWS credit lines from the funding proposal (USD, whole 8-month project).
PROJECT_MONTHS = 8
HOSTING_ALLOCATION = 350  # backend hosting, database, API, monitoring
RESEARCH_DATA_GB = 200  # assumed peak: consented recordings, transcripts, datasets


def allocation_fit() -> None:
    pilot = sum({**FIXED, **variable_costs(SCENARIOS["Pilot"])}.values())
    waf = OPTIONAL["WAF on CloudFront (1 ACL, 5 rules)"]
    fargate = OPTIONAL["Fargate instead of Lambda (2 tasks + ALB)"]
    rds = OPTIONAL["Keep Postgres in production (RDS t4g.micro, Multi-AZ)"]
    options = {
        "Recommended: Lambda, DynamoDB, no production Postgres": pilot,
        "Recommended + WAF": pilot + waf,
        "Fargate instead of Lambda": pilot + fargate,
        "Fargate + Postgres in production + WAF": pilot + fargate + rds + waf,
    }
    print(f"| Hosting setup (pilot scale) | Monthly | {PROJECT_MONTHS} months | "
          f"vs ${HOSTING_ALLOCATION} line |")
    print("|---|---:|---:|---|")
    for name, monthly in options.items():
        total = monthly * PROJECT_MONTHS
        verdict = "fits" if total <= HOSTING_ALLOCATION else f"over by ${total - HOSTING_ALLOCATION:,.0f}"
        print(f"| {name} | ${monthly:,.2f} | ${total:,.0f} | {verdict} |")
    research = RESEARCH_DATA_GB * PRICE["s3_gb"] * PROJECT_MONTHS
    print()
    print(f"S3 research data: {RESEARCH_DATA_GB} GB for {PROJECT_MONTHS} months = ${research:,.0f}")


def main() -> None:
    names = list(SCENARIOS)
    rows = {}
    for name, learners in SCENARIOS.items():
        for item, cost in {**FIXED, **variable_costs(learners)}.items():
            rows.setdefault(item, {})[name] = cost
    header = "| Item | " + " | ".join(f"{n} ({SCENARIOS[n]:,} learners)" for n in names) + " |"
    print(header)
    print("|---|" + "---:|" * len(names))
    for item, by in rows.items():
        print(f"| {item} | " + " | ".join(f"${by[n]:,.2f}" for n in names) + " |")
    totals = {n: sum(by[n] for by in rows.values()) for n in names}
    print("| **Total (Lambda option)** | " + " | ".join(f"**${totals[n]:,.2f}**" for n in names) + " |")
    print()
    print("| Optional add-on | Monthly |")
    print("|---|---:|")
    for item, cost in OPTIONAL.items():
        print(f"| {item} | {'see note' if cost is None else f'${cost:,.2f}'} |")


if __name__ == "__main__":
    main()
    print()
    allocation_fit()
