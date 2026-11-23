output "security_log_bucket" {
  value = aws_s3_bucket.logs.bucket
}

output "trail_arn" {
  value = aws_cloudtrail.this.arn
}

output "alert_topic_arn" {
  value = aws_sns_topic.alerts.arn
}

output "guardduty_detector_id" {
  value = aws_guardduty_detector.this.id
}
