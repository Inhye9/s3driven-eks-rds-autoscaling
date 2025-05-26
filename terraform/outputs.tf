output "s3_bucket_name" {
  description = "Name of the created S3 bucket"
  value       = aws_s3_bucket.autoscale_bucket.id
}

output "autoscale_handler_lambda_arn" {
  description = "ARN of the autoscale handler Lambda function"
  value       = aws_lambda_function.autoscale_handler_lambda.arn
}

output "rds_handler_lambda_arn" {
  description = "ARN of the RDS handler Lambda function"
  value       = aws_lambda_function.rds_handler_lambda.arn
}
