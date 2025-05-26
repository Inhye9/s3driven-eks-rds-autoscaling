variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "ap-northeast-2"
}

variable "aws_account_id" {
  description = "AWS Account ID"
  type        = string
}

variable "s3_bucket_name" {
  description = "Name of the S3 bucket for autoscale schedules"
  type        = string
}

variable "lambda_role_name" {
  description = "Name of the IAM role for the Lambda function"
  type        = string
  default     = "autoscale-handler-lambda-role"
}

variable "rds_lambda_role_name" {
  description = "Name of the IAM role for the RDS handler Lambda function"
  type        = string
  default     = "autoscale-rds-handler-lambda-role"
}

variable "autoscale_handler_lambda_name" {
  description = "Name of the autoscale handler Lambda function"
  type        = string
  default     = "autoscale-handler-lmb"
}

variable "rds_handler_lambda_name" {
  description = "Name of the RDS handler Lambda function"
  type        = string
  default     = "autoscale-rds-handler-lmb"
}

variable "lambda_zip_path" {
  description = "Path to the Lambda function zip file"
  type        = string
  default     = "lambda/autoscale_handler.zip"
}

variable "rds_lambda_zip_path" {
  description = "Path to the RDS Lambda function zip file"
  type        = string
  default     = "lambda/autoscale-rds-handler.zip"
}

variable "teams_webhook_url" {
  description = "Microsoft Teams webhook URL for notifications"
  type        = string
}

variable "workbench_ec2_tag" {
  description = "Tag name for the workbench EC2 instance"
  type        = string
  default     = "workbench-ec2"
}
