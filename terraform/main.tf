provider "aws" {
  region = var.aws_region
}

# S3 버킷 생성
resource "aws_s3_bucket" "autoscale_bucket" {
  bucket = var.s3_bucket_name
  tags = local.default_tags
}

# S3 버킷 알림 설정
resource "aws_s3_bucket_notification" "bucket_notification" {
  bucket = aws_s3_bucket.autoscale_bucket.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.autoscale_handler_lambda.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "docs/"
    filter_suffix       = ".csv"
  }

  depends_on = [aws_lambda_permission.allow_bucket]
}

# Lambda 함수에 S3 트리거 권한 부여
resource "aws_lambda_permission" "allow_bucket" {
  statement_id  = "AllowExecutionFromS3Bucket"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.autoscale_handler_lambda.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.autoscale_bucket.arn
}

# IAM Role for Lambda
resource "aws_iam_role" "lambda_role" {
  name = var.lambda_role_name

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
  tags = local.default_tags
}

# IAM Policy for Lambda
resource "aws_iam_policy" "lambda_policy" {
  name        = "${var.lambda_role_name}-policy"
  description = "Policy for autoscale_handler Lambda function"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::${var.s3_bucket_name}/*",
          "arn:aws:s3:::${var.s3_bucket_name}"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:DescribeInstances"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ssm:SendCommand",
          "ssm:GetCommandInvocation"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "scheduler:CreateSchedule",
          "scheduler:DeleteSchedule",
          "scheduler:GetSchedule",
          "scheduler:ListSchedules"
        ]
        Resource = [
          "arn:aws:scheduler:${var.aws_region}:*:schedule/autoscale-rds-sg/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = [
          "arn:aws:lambda:${var.aws_region}:*:function:${var.rds_handler_lambda_name}:*",
          "arn:aws:lambda:${var.aws_region}:*:function:${var.rds_handler_lambda_name}"
        ]
      }
    ]
  })
  tags = local.default_tags
}

# Attach policy to role
resource "aws_iam_role_policy_attachment" "lambda_policy_attachment" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.lambda_policy.arn
}

# Lambda 함수 코드 패키징을 위한 데이터 소스
data "archive_file" "autoscale_handler_zip" {
  type        = "zip"
  # source_file = "${path.module}/src/autoscale_handler.py"
  # output_path = "${path.module}/lambda/autoscale_handler.zip"
  source_file = "../src/autoscale_handler.py"
  output_path = "../lambda/autoscale_handler.zip"
}

data "archive_file" "rds_handler_zip" {
  type        = "zip"
  # source_file = "${path.module}/src/autoscale-rds-handler.py"
  # output_path = "${path.module}/lambda/autoscale-rds-handler.zip"
  source_file = "../src/autoscale-rds-handler.py"
  output_path = "../lambda/autoscale-rds-handler.zip"
}

# Lambda 함수 리소스 수정
resource "aws_lambda_function" "autoscale_handler_lambda" {
  function_name    = var.autoscale_handler_lambda_name
  role             = aws_iam_role.lambda_role.arn
  handler          = "autoscale_handler.lambda_handler"
  runtime          = "python3.11"
  timeout          = 300
  memory_size      = 256
  filename         = data.archive_file.autoscale_handler_zip.output_path
  source_code_hash = data.archive_file.autoscale_handler_zip.output_base64sha256
  # filename         = var.lambda_zip_path
  # source_code_hash = filebase64sha256(var.lambda_zip_path)

  environment {
    variables = {
      TEAMS_WEBHOOK = var.teams_webhook_url
      WORKBENCH_EC2_TAG = var.workbench_ec2_tag
      ACCOUNT_ID = var.aws_account_id
    }
  }

  tags = local.default_tags
}

resource "aws_lambda_function" "rds_handler_lambda" {
  function_name    = var.rds_handler_lambda_name
  role             = aws_iam_role.rds_lambda_role.arn
  handler          = "autoscale-rds-handler.lambda_handler"
  runtime          = "python3.11"
  timeout          = 300
  memory_size      = 256
  filename         = data.archive_file.rds_handler_zip.output_path
  source_code_hash = data.archive_file.rds_handler_zip.output_base64sha256
  # filename         = var.rds_lambda_zip_path
  # source_code_hash = filebase64sha256(var.rds_lambda_zip_path)

  tags = local.default_tags
}



# IAM Role for RDS Lambda
resource "aws_iam_role" "rds_lambda_role" {
  name = var.rds_lambda_role_name

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = local.default_tags
}

# IAM Policy for RDS Lambda
resource "aws_iam_policy" "rds_lambda_policy" {
  name        = "${var.rds_lambda_role_name}-policy"
  description = "Policy for RDS handler Lambda function"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "rds:DescribeDBClusters",
          "rds:DescribeDBInstances",
          "rds:CreateDBInstance",
          "rds:DeleteDBInstance"
        ]
        Resource = [
          "arn:aws:rds:${var.aws_region}:*:cluster:autoscale-*",
          "arn:aws:rds:${var.aws_region}:*:db:*"
        ]
      }
    ]
  })

  tags = local.default_tags
}

# Attach policy to RDS Lambda role
resource "aws_iam_role_policy_attachment" "rds_lambda_policy_attachment" {
  role       = aws_iam_role.rds_lambda_role.name
  policy_arn = aws_iam_policy.rds_lambda_policy.arn
}
