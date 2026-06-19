#!/bin/bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════
# EC2 User Data — bootstrap script for Code RAG server
# ═══════════════════════════════════════════════════════════

echo ">>> Installing Docker..."
yum update -y
yum install -y docker git jq
systemctl enable docker
systemctl start docker
usermod -aG docker ec2-user

# Install Docker Compose
COMPOSE_VERSION="v2.27.1"
curl -SL "https://github.com/docker/compose/releases/download/$${COMPOSE_VERSION}/docker-compose-linux-x86_64" \
  -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# ── Fetch secrets from Secrets Manager ────────────────────
echo ">>> Fetching secrets..."
SECRETS=$(aws secretsmanager get-secret-value \
  --secret-id "${secret_arn}" \
  --region "${aws_region}" \
  --query SecretString \
  --output text)

POSTGRES_URL=$(echo "$SECRETS" | jq -r '.POSTGRES_URL')
GOOGLE_API_KEY=$(echo "$SECRETS" | jq -r '.GOOGLE_API_KEY')
GITHUB_TOKEN=$(echo "$SECRETS" | jq -r '.GITHUB_TOKEN')
JWT_SECRET=$(echo "$SECRETS" | jq -r '.JWT_SECRET')
S3_BUCKET=$(echo "$SECRETS" | jq -r '.S3_BUCKET')

# ── Create app directory ──────────────────────────────────
APP_DIR="/home/ec2-user/app"
mkdir -p "$APP_DIR"

# ── Write .env file ───────────────────────────────────────
cat > "$APP_DIR/.env" <<EOF
POSTGRES_URL=$POSTGRES_URL
GOOGLE_API_KEY=$GOOGLE_API_KEY
GITHUB_TOKEN=$GITHUB_TOKEN
AWS_REGION=${aws_region}
S3_BUCKET=$S3_BUCKET
DYNAMODB_REPOS_TABLE=repos
DYNAMODB_SESSIONS_TABLE=sessions
JWT_SECRET=$JWT_SECRET
EOF

# ── Write production docker-compose ───────────────────────
cat > "$APP_DIR/docker-compose.yml" <<'COMPOSE'
services:
  fastapi:
    image: ghcr.io/coderag/pipeline:latest
    container_name: coderag-fastapi
    ports:
      - "8000:8000"
    env_file: .env
    environment:
      - AWS_ENDPOINT_URL=
    restart: unless-stopped

  gateway:
    image: ghcr.io/coderag/gateway:latest
    container_name: coderag-gateway
    ports:
      - "8080:8080"
    env_file: .env
    environment:
      - GATEWAY_FASTAPI_BASE_URL=http://fastapi:8000
      - AWS_ENDPOINT_URL=
      - SERVER_PORT=8080
    depends_on:
      - fastapi
    restart: unless-stopped
COMPOSE

# ── Initialize RDS with pgvector ──────────────────────────
echo ">>> Initializing pgvector on RDS..."
yum install -y postgresql16

# Extract host/port from endpoint
DB_HOST=$(echo "${db_endpoint}" | cut -d: -f1)
DB_PORT=$(echo "${db_endpoint}" | cut -d: -f2)
DB_PASS=$(echo "$POSTGRES_URL" | sed -n 's|.*://[^:]*:\([^@]*\)@.*|\1|p')

PGPASSWORD="$DB_PASS" psql -h "$DB_HOST" -p "$DB_PORT" -U coderag -d coderag <<SQL
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS code_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_id VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    language VARCHAR(20) NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding vector(384) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_code_chunks_repo_id ON code_chunks(repo_id);
CREATE INDEX IF NOT EXISTS idx_code_chunks_embedding
    ON code_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
SQL

echo ">>> pgvector initialized."

# ── Set ownership ─────────────────────────────────────────
chown -R ec2-user:ec2-user "$APP_DIR"

echo ">>> Bootstrap complete. Run: cd /home/ec2-user/app && docker-compose up -d"
