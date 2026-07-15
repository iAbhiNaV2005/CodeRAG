#!/bin/bash
set -euo pipefail

echo ">>> Installing Docker and helpers..."
yum update -y
yum install -y docker git jq

if ! command -v aws >/dev/null 2>&1; then
  yum install -y awscli || yum install -y awscli-2
fi

systemctl enable docker
systemctl start docker
usermod -aG docker ec2-user

if ! command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_VERSION="v2.27.1"
  curl -SL "https://github.com/docker/compose/releases/download/$${COMPOSE_VERSION}/docker-compose-linux-x86_64" \
    -o /usr/local/bin/docker-compose
  chmod +x /usr/local/bin/docker-compose
fi

echo ">>> Fetching application secrets..."
SECRETS=$(aws secretsmanager get-secret-value \
  --secret-id "${secret_arn}" \
  --region "${aws_region}" \
  --query SecretString \
  --output text)

POSTGRES_URL=$(echo "$SECRETS" | jq -r '.POSTGRES_URL')
POSTGRES_PASSWORD=$(echo "$SECRETS" | jq -r '.POSTGRES_PASSWORD')
GOOGLE_API_KEY=$(echo "$SECRETS" | jq -r '.GOOGLE_API_KEY')
GITHUB_TOKEN=$(echo "$SECRETS" | jq -r '.GITHUB_TOKEN')
JWT_SECRET=$(echo "$SECRETS" | jq -r '.JWT_SECRET')
S3_BUCKET=$(echo "$SECRETS" | jq -r '.S3_BUCKET')

APP_DIR="/home/ec2-user/app"
mkdir -p "$APP_DIR"

echo ">>> Writing environment file..."
cat > "$APP_DIR/.env" <<EOF
POSTGRES_URL=$POSTGRES_URL
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
GOOGLE_API_KEY=$GOOGLE_API_KEY
GITHUB_TOKEN=$GITHUB_TOKEN
JWT_SECRET=$JWT_SECRET
AWS_REGION=${aws_region}
AWS_ENDPOINT_URL=
S3_BUCKET=$S3_BUCKET
DYNAMODB_REPOS_TABLE=repos
DYNAMODB_SESSIONS_TABLE=sessions
DYNAMODB_RATE_LIMITS_TABLE=rate_limits
EOF

chmod 600 "$APP_DIR/.env"

echo ">>> Writing pgvector schema..."
cat > "$APP_DIR/init.sql" <<'SQL'
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

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

CREATE INDEX IF NOT EXISTS idx_code_chunks_embedding
    ON code_chunks USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_code_chunks_repo_id
    ON code_chunks (repo_id);

CREATE INDEX IF NOT EXISTS idx_code_chunks_repo_language
    ON code_chunks (repo_id, language);
SQL

echo ">>> Writing Docker Compose stack..."
cat > "$APP_DIR/docker-compose.yml" <<'COMPOSE'
services:
  postgres:
    image: pgvector/pgvector:pg16
    container_name: coderag-postgres
    environment:
      POSTGRES_DB: coderag
      POSTGRES_USER: coderag
      POSTGRES_PASSWORD: $${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U coderag -d coderag"]
      interval: 10s
      timeout: 5s
      retries: 10
    restart: unless-stopped

  fastapi:
    image: ${pipeline_image}
    container_name: coderag-fastapi
    env_file: .env
    environment:
      POSTGRES_URL: postgresql://coderag:$${POSTGRES_PASSWORD}@postgres:5432/coderag
      AWS_ENDPOINT_URL: ""
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped

  gateway:
    image: ${gateway_image}
    container_name: coderag-gateway
    ports:
      - "8080:8080"
    env_file: .env
    environment:
      GATEWAY_FASTAPI_BASE_URL: http://fastapi:8000
      AWS_ENDPOINT_URL: ""
      SERVER_PORT: "8080"
      JAVA_TOOL_OPTIONS: "-XX:MaxRAMPercentage=60"
    depends_on:
      - fastapi
    restart: unless-stopped

volumes:
  postgres_data:
COMPOSE

chown -R ec2-user:ec2-user "$APP_DIR"

echo ">>> Starting Code RAG backend..."
cd "$APP_DIR"
docker-compose pull
docker-compose up -d

echo ">>> Bootstrap complete. Gateway should be available on port 8080."
