# 초기화
terraform init

# 계획 확인
terraform plan -var-file=test.tfvars

# 배포
terraform apply -var-file=test.tfvars
