# Setting Up Find

This guide covers deploying and configuring Find for your environment.

## Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Redis 7+
- One of: OpenSearch 2.x, TypeSense 0.25+, or Meilisearch 1.x
- Docker & Docker Compose (for development)

## Quick Start (Development)

```bash
# Clone the repository
git clone https://github.com/suitenumerique/find.git
cd find

# Copy environment file
cp env.d/development/common.dist.env env.d/development/common.env

# Start services
make bootstrap

# Run migrations
make migrate

# Create the unified index
make create-index
```

Find is now running at `http://localhost:8081`.

## Configuration

### Search Backend Selection

Find supports multiple search backends. Set the `SEARCH_BACKEND` environment variable:

```bash
# OpenSearch (default)
SEARCH_BACKEND=opensearch

# TypeSense
SEARCH_BACKEND=typesense

# Meilisearch
SEARCH_BACKEND=meilisearch
```

Each backend requires its own configuration. See [Environment Variables](env.md) for details.

### Database Configuration

```bash
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=find
POSTGRES_USER=find
POSTGRES_PASSWORD=<secure-password>
```

### Redis Configuration

```bash
REDIS_URL=redis://localhost:6379/0
```

## Unified Index

Find uses a single unified index for all documents. The index is created automatically on first startup, or manually:

```bash
# Create the index with proper mappings
make create-index

# Or via Django management command
python manage.py create_index
```

### Index Structure

The unified index contains documents from all services:

```json
{
  "mappings": {
    "properties": {
      "id": { "type": "keyword" },
      "service": { "type": "keyword" },
      "title": { "type": "text", "analyzer": "french" },
      "content": { "type": "text", "analyzer": "french" },
      "users": { "type": "keyword" },
      "groups": { "type": "keyword" },
      "reach": { "type": "keyword" },
      "tags": { "type": "keyword" },
      "path": { "type": "keyword" },
      "depth": { "type": "integer" },
      "is_active": { "type": "boolean" },
      "created_at": { "type": "date" },
      "updated_at": { "type": "date" }
    }
  }
}
```

### Language Support

Find supports multiple languages with appropriate analyzers:

| Language | Analyzer |
|----------|----------|
| French | `french` with elision, stopwords |
| English | `english` with stemming |
| German | `german` with compound words |
| Dutch | `dutch` with stemming |

Configure the default language:

```bash
SEARCH_DEFAULT_LANGUAGE=french
```

## Service Registration

Services (applications) must be registered before they can index documents.

### Create a Service

```bash
# Via Django admin
python manage.py createsuperuser
# Then visit http://localhost:8081/admin/core/service/

# Or via management command
python manage.py create_service --name docs --client-id docs-client-id
```

### Service Token

Each service receives a 50-character token for authentication:

```
Token: 8f3a9b2c4d5e6f7g8h9i0j1k2l3m4n5o6p7q8r9s0t1u2v3w4x
```

**Keep this token secure.** It grants full write access to documents for that service.

### Service Configuration

| Field | Description |
|-------|-------------|
| `name` | Service identifier (e.g., "docs", "drive") |
| `client_id` | OIDC client ID for the service |
| `token` | Authentication token for indexing API |
| `is_active` | Enable/disable the service |

## Access Control Setup

Documents are indexed with access control fields that determine who can search them.

### Access Control Fields

| Field | Type | Description |
|-------|------|-------------|
| `users` | array | User SUBs who can access |
| `groups` | array | Group slugs who can access |
| `reach` | string | Visibility level |

### Reach Levels

| Value | Who Can See |
|-------|-------------|
| `public` | Anyone (requires explicit visit) |
| `authenticated` | Any authenticated user (requires explicit visit) |
| `restricted` | Only users in `users` or `groups` |

### Example Document with Access Control

```json
{
  "id": "doc-123",
  "service": "docs",
  "title": "Project Roadmap",
  "content": "Q1 objectives...",
  "users": ["user-sub-alice", "user-sub-bob"],
  "groups": ["engineering-team"],
  "reach": "restricted"
}
```

This document is visible only to:
- Users with SUB `user-sub-alice` or `user-sub-bob`
- Users who are members of `engineering-team` group

## Health Checks

Find exposes health check endpoints:

```bash
# Overall health
curl http://localhost:8081/api/v1.0/health/

# Search backend health
curl http://localhost:8081/api/v1.0/health/search/
```

## Production Deployment

### Environment Variables

For production, ensure these are set:

```bash
# Security
DJANGO_SECRET_KEY=<cryptographically-secure-key>
DJANGO_ALLOWED_HOSTS=find.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://find.example.com

# Search Backend
SEARCH_BACKEND=opensearch
OPENSEARCH_HOST=opensearch.internal
OPENSEARCH_PORT=9200
OPENSEARCH_USE_SSL=true

# Database
POSTGRES_HOST=postgres.internal
POSTGRES_PASSWORD=<secure-password>

# Redis
REDIS_URL=redis://redis.internal:6379/0
```

See [Environment Variables](env.md) for complete reference.

### Scaling

| Component | Scaling Strategy |
|-----------|-----------------|
| **API** | Horizontal (multiple replicas behind load balancer) |
| **Celery Workers** | Horizontal (increase for indexing throughput) |
| **Search Backend** | Per backend documentation (cluster mode) |
| **PostgreSQL** | Vertical (or managed service with replicas) |
| **Redis** | Vertical (or Redis Cluster for high availability) |

### Monitoring

Key metrics to monitor:

- API response times (p50, p95, p99)
- Search query latency
- Indexing queue depth (Celery)
- Search backend health
- Document count by service

## Troubleshooting

### Index Not Created

```bash
# Check search backend connectivity
curl http://localhost:9200/_cluster/health

# Recreate index
make create-index
```

### Service Cannot Index

1. Verify service token is correct
2. Check service is active in database
3. Verify search backend is healthy

### Search Returns No Results

1. Verify documents are indexed: `GET /api/v1.0/documents/count/`
2. Check user has access (correct SUB, group membership)
3. Verify `reach` level is appropriate

## Next Steps

- [Core Concepts](concepts.md) - Understand unified index, claims, abstraction
- [Architecture](architecture.md) - System architecture overview
- [Integration: Docs](setup-for-docs.md) - Integrate with Docs application
- [Integration: Drive](setup-for-drive.md) - Integrate with Drive application
- [Environment Variables](env.md) - Complete configuration reference
