# Code RAG AWS Redeploy Runbook

This is the low-cost resume-demo deployment:

- Vercel hosts the Next.js frontend.
- One EC2 instance runs the Spring Boot gateway, FastAPI RAG service, and PostgreSQL/pgvector in Docker.
- DynamoDB stores repo status, chat sessions, and rate-limit counters.
- S3 stores raw fetched repository files with a short lifecycle expiry.
- No RDS instance is created.
- Lambda + EventBridge automatically stops EC2 at midnight IST and starts at 8 AM IST.

## 1. Build and Push Backend Images

From the repository root, build and push both backend containers to GHCR:

PowerShell:

```powershell
$env:GHCR_USER = "iAbhiNaV2005"
$env:GHCR_TOKEN = "YOUR_GITHUB_PAT_WITH_WRITE_PACKAGES"

$env:GHCR_TOKEN | docker login ghcr.io -u $env:GHCR_USER --password-stdin

docker build -t ghcr.io/$env:GHCR_USER/coderag-pipeline:latest .\rag-pipeline
docker push ghcr.io/$env:GHCR_USER/coderag-pipeline:latest

docker build -t ghcr.io/$env:GHCR_USER/coderag-gateway:latest .\gateway
docker push ghcr.io/$env:GHCR_USER/coderag-gateway:latest
```

Make the GHCR packages **public** on GitHub (Settings → Packages → Visibility) so EC2 can pull without extra auth.

## 2. Configure Terraform

```powershell
cd .\infra\terraform
copy terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` with your real secrets (db_password, jwt_secret, google_api_key, github_token).

## 3. Deploy AWS

```powershell
terraform init
terraform apply
```

After apply, copy the outputs:

```powershell
terraform output gateway_url
terraform output ec2_instance_id
terraform output auto_schedule
```

The backend bootstraps automatically. Give EC2 3-5 minutes, then check:

```powershell
curl http://YOUR_EC2_PUBLIC_IP:8080/health
```

If it is not ready yet, SSH in and inspect:

```bash
ssh -i CodeRAG.pem ec2-user@YOUR_EC2_PUBLIC_IP
cd /home/ec2-user/app
docker-compose ps
docker-compose logs -f gateway
docker-compose logs -f fastapi
```

## 4. Reconnect Vercel Frontend

In Vercel, set this environment variable for the frontend project:

```text
API_PROXY_URL=http://YOUR_EC2_PUBLIC_IP:8080
```

Then redeploy the frontend. The app will keep calling `/api/*`, and Vercel will proxy those requests to your new EC2 gateway.

## 5. Save Credits

**Automated (default):** EC2 auto-stops at midnight IST and auto-starts at 8 AM IST via Lambda + EventBridge. This saves ~67% on EC2 compute. Set `enable_auto_schedule = false` in terraform.tfvars to disable.

**Manual override:**

```powershell
# Stop immediately
aws ec2 stop-instances --instance-ids (terraform output -raw ec2_instance_id)

# Start manually
aws ec2 start-instances --instance-ids (terraform output -raw ec2_instance_id)
```

When stopped, EC2 compute billing pauses, but the EBS volume still persists and costs a small amount. Your pgvector data is on that EBS-backed Docker volume.

To delete everything:

```powershell
terraform destroy
```

Use destroy only when you are okay losing the EC2-hosted Postgres data.
