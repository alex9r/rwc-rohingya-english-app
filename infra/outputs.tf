output "buckets" {
  value = { for k, b in aws_s3_bucket.this : k => b.bucket }
}

output "tables" {
  value = {
    content    = aws_dynamodb_table.content.name
    progress   = aws_dynamodb_table.progress.name
    review_log = aws_dynamodb_table.review_log.name
  }
}

output "media_url" {
  value = "https://${aws_cloudfront_distribution.media.domain_name}"
}

output "policy_arns" {
  description = "Attach to roles once compute (Lambda or ECS) is chosen."
  value = {
    api               = aws_iam_policy.api.arn
    reviewer          = aws_iam_policy.reviewer.arn
    recording_deleter = aws_iam_policy.recording_deleter.arn
    research_uploader = aws_iam_policy.research_uploader.arn
    research_reader   = aws_iam_policy.research_reader.arn
  }
}
