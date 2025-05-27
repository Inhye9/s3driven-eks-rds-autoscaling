# S3-Driven Scheduled Autoscaling for EKS Pods and Aurora Read Replicas

This solution automates **proactive infrastructure scaling** based on scheduled entries defined in a `.csv` file uploaded to Amazon S3. The system supports two types of scheduled actions:

1. **EKS pod scaling** via crontab on a Workbench EC2 instance.
2. **Aurora PostgreSQL read replica scaling** via EventBridge Scheduler triggering a Lambda function.


## 🧩 Architecture Overview

![architecture-diagram](./docs/architecture.png) 


## 📂 Project Structure
```
.
├── src/
│ ├── autoscale_handler.py # Lambda handler triggered by schedule
│ ├── autoscale-rds-handler.py # Functions to scale EKS node groups
│ ├── init_crontab.sh # Bash shell to remove previous #autoreg cron on crontab 
│ └── cron_autoscale.sh # Bash shell executed by cron for managing hpa 
├── events/
│ └── scheduled_event.json # Example EventBridge Scheduler event payload
├── docs/
│ ├── architecture.png # Architecture diagram
│ └── autoscale-schdule.csv # csv file to upload in s3 bucket 
├── role/
│ ├── lambda-role.json # iam role policy for autoscale-handler.py 
│ └── lambda-rds-role.json # iam role policy for autoscale-rds-hanlder.py
├── terraform/ 
│ ├── test.tfvars # variables --var-file=test.tfvars
│ ├── main.tf
│ ├── tag.tf
│ ├── output.tf
│ ├── variables.tf
│ └── README.md # Terraform documentation 
└── README.md # Project documentation

```


## ⚙️ Requirements

- **S3 Bucket**
  - Trigger: `s3:ObjectCreated:*` event connected to a Lambda function

- **Lambda Execution Role** must include permissions to:
  - Read objects from S3
  - use SSM to access EC2 for crontab updates
  - Create EventBridge Scheduler rules
  - Modify RDS (e.g., `ModifyDBCluster`, `CreateDBInstance`)

- **Workbench EC2 Instance** must:
  - Be reachable via SSH from Lambda
  - Have `kubectl` installed and configured for EKS access
  - Have the `cron_autoscale.sh` and `init_crontab.sh` deployed and executable


## 🛠️ Workflow

### 1. Upload Schedule

Upload a `.csv` file to the configured S3 bucket

### 2. Lambda Triggered

When the `.csv` file is uploaded to S3, a Lambda function is automatically triggered.

The Lambda function performs the following actions:

#### For EKS entries:
- Connects to the EC2 instance (workbench or jumpbox) via SSH or SSM
- Execute `init_crontab.sh` to remove expired cron jobs marked with #autoreg tags 
- Adds a `crontab` entry that schedules the execution of `cron_autoscale.sh` at the specified time

#### For RDS entries:
- Remove previous ** 
- Creates an **EventBridge Scheduler** rule
- The rule is configured to invoke the `autoscale-rds-handler.py` Lambda function at the defined time


### 3. EKS Pod Scaling (via EC2 crontab)

At the scheduled time, the `cron_autoscale.sh`script is executed on the EC2 instance:


## 🛠️ Deployment Steps
### 1️⃣ Clone the Repository

```bash
git clone https://github.com/yourusername/s3driven-eks-rds-autoscaling.git
cd s3driven-eks-rds-autoscaling
```

### 2️⃣ Configure Terraform Variables
```bash 
cd terraform
cp test.tfvars.example test.tfvars
# ✏️ Edit test.tfvars with your AWS account details and configuration
```

### 3️⃣ Deploy Infrastructure with Terraform
```bash 
terraform init
terraform plan --var-file=test.tfvars
terraform apply --var-file=test.tfvars
```

### 4️⃣ Deploy Shell Scripts to EC2
```bash 
# Create directories on EC2 via SSM
aws ssm send-command \
  --instance-ids "<instance-id>" \
  --document-name "AWS-RunShellScript" \
  --parameters "commands=[
    'mkdir -p /apps/autoscale/bin',
    'mkdir -p /apps/autoscale/logs'
  ]"

# Upload scripts to S3 temporarily
aws s3 cp src/cron_autoscale.sh s3://your-bucket-name/scripts/
aws s3 cp src/init_crontab.sh s3://your-bucket-name/scripts/

# Download scripts on EC2 and set permissions
aws ssm send-command \
  --instance-ids "<instance-id>" \
  --document-name "AWS-RunShellScript" \
  --parameters "commands=[
    'aws s3 cp s3://your-bucket-name/scripts/cron_autoscale.sh /apps/autoscale/bin/',
    'aws s3 cp s3://your-bucket-name/scripts/init_crontab.sh /apps/autoscale/bin/',
    'chmod +x /apps/autoscale/bin/cron_autoscale.sh',
    'chmod +x /apps/autoscale/bin/init_crontab.sh'
  ]"
```

### 5️⃣ Test the Deployment
```bash 
# Upload a test schedule CSV to trigger the workflow
aws s3 cp docs/autoscale-schedule.csv s3://your-bucket-name/docs/

# View Lambda execution logs
aws logs get-log-events \
  --log-group-name "/aws/lambda/autoscale-handler-lmb" \
  --log-stream-name "$(aws logs describe-log-streams \
    --log-group-name "/aws/lambda/autoscale-handler-lmb" \
    --query 'logStreams[0].logStreamName' \
    --output text)"
```

### 6️⃣ Verify Crontab Entries on EC2
```bash 
aws ssm send-command \
  --instance-ids "i-0123456789abcdef0" \
  --document-name "AWS-RunShellScript" \
  --parameters "commands=['crontab -l']"
``` 

### 7️⃣ Verify EventBridge Scheduler Rules
```bash
aws scheduler list-schedules \
  --group-name "autoscale-rds-sg" \
  --name-prefix "autoscale-"
```


## 📌 Notes
- The CSV file format must follow the specified structure with columns for date, time, scaling percentage, and event DB flag.

- Ensure the workbench EC2 instance has the necessary IAM permissions to execute kubectl commands on your EKS cluster.

- For security best practices, limit the permissions of the Lambda execution roles to only what's necessary.

- EventBridge Scheduler rules are created with unique names based on the date and action to prevent duplicates.

- The solution automatically cleans up expired cron entries and EventBridge rules when new schedules are uploaded.

- Monitor CloudWatch logs for any execution errors in the Lambda functions.