# Environment Variables

Complete reference for Find configuration.

## Core Settings

### Django Configuration

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `DJANGO_SECRET_KEY` | Cryptographic signing key | - | **Yes** |
| `DJANGO_DEBUG` | Enable debug mode | `false` | No |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated allowed hostnames | `*` | Production |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Comma-separated trusted origins for CSRF | - | Production |
| `DJANGO_SETTINGS_MODULE` | Settings module path | `find.settings` | No |

### Database (PostgreSQL)

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `POSTGRES_HOST` | Database hostname | `localhost` | **Yes** |
| `POSTGRES_PORT` | Database port | `5432` | No |
| `POSTGRES_DB` | Database name | `find` | **Yes** |
| `POSTGRES_USER` | Database user | `find` | **Yes** |
| `POSTGRES_PASSWORD` | Database password | - | **Yes** |

### Redis / Celery

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379/0` | **Yes** |
| `CELERY_BROKER_URL` | Celery broker URL | `$REDIS_URL` | No |
| `CELERY_RESULT_BACKEND` | Celery result backend | `$REDIS_URL` | No |

## Search Backend Configuration

### Backend Selection

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `SEARCH_BACKEND` | Search backend to use | `opensearch` | No |
| `SEARCH_INDEX_NAME` | Name of the unified index | `find` | No |
| `SEARCH_DEFAULT_LANGUAGE` | Default search language | `french` | No |

Supported values for `SEARCH_BACKEND`:
- `opensearch` - OpenSearch 2.x
- `typesense` - TypeSense 0.25+
- `meilisearch` - Meilisearch 1.x

### OpenSearch Configuration

Required when `SEARCH_BACKEND=opensearch`:

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `OPENSEARCH_HOST` | OpenSearch hostname | `localhost` | **Yes** |
| `OPENSEARCH_PORT` | OpenSearch port | `9200` | No |
| `OPENSEARCH_USE_SSL` | Enable SSL/TLS | `false` | No |
| `OPENSEARCH_VERIFY_CERTS` | Verify SSL certificates | `true` | No |
| `OPENSEARCH_USER` | OpenSearch username | - | If auth enabled |
| `OPENSEARCH_PASSWORD` | OpenSearch password | - | If auth enabled |
| `OPENSEARCH_CA_CERTS` | Path to CA certificate | - | If custom CA |

### TypeSense Configuration

Required when `SEARCH_BACKEND=typesense`:

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `TYPESENSE_HOST` | TypeSense hostname | `localhost` | **Yes** |
| `TYPESENSE_PORT` | TypeSense port | `8108` | No |
| `TYPESENSE_PROTOCOL` | Protocol (http/https) | `http` | No |
| `TYPESENSE_API_KEY` | TypeSense API key | - | **Yes** |

### Meilisearch Configuration

Required when `SEARCH_BACKEND=meilisearch`:

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `MEILISEARCH_HOST` | Meilisearch hostname | `localhost` | **Yes** |
| `MEILISEARCH_PORT` | Meilisearch port | `7700` | No |
| `MEILISEARCH_PROTOCOL` | Protocol (http/https) | `http` | No |
| `MEILISEARCH_API_KEY` | Meilisearch master key | - | **Yes** |

## Authentication

### OIDC Configuration

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `OIDC_OP_ISSUER` | OIDC provider issuer URL | - | **Yes** |
| `OIDC_OP_JWKS_ENDPOINT` | JWKS endpoint URL | `{issuer}/.well-known/jwks.json` | No |
| `OIDC_OP_AUTHORIZATION_ENDPOINT` | Authorization endpoint | Auto-discovered | No |
| `OIDC_OP_TOKEN_ENDPOINT` | Token endpoint | Auto-discovered | No |
| `OIDC_OP_USER_ENDPOINT` | Userinfo endpoint | Auto-discovered | No |
| `OIDC_RP_CLIENT_ID` | Find's OIDC client ID | - | **Yes** |
| `OIDC_RP_CLIENT_SECRET` | Find's OIDC client secret | - | **Yes** |
| `OIDC_VERIFY_SSL` | Verify OIDC provider SSL | `true` | No |
| `OIDC_AUDIENCE` | Expected audience claim | `$OIDC_RP_CLIENT_ID` | No |

### User Claims Mapping

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `OIDC_CLAIM_SUB` | Claim for user identifier | `sub` | No |
| `OIDC_CLAIM_EMAIL` | Claim for email | `email` | No |
| `OIDC_CLAIM_GROUPS` | Claim for group memberships | `groups` | No |

## Search Behavior

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `SEARCH_MAX_RESULTS` | Maximum results per search | `100` | No |
| `SEARCH_DEFAULT_PAGE_SIZE` | Default page size | `20` | No |
| `SEARCH_HIGHLIGHT_ENABLED` | Enable result highlighting | `true` | No |
| `SEARCH_HIGHLIGHT_FRAGMENT_SIZE` | Highlight fragment size | `150` | No |
| `SEARCH_FUZZINESS` | Fuzzy matching level | `AUTO` | No |

## Indexing Behavior

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `INDEX_BATCH_SIZE` | Bulk indexing batch size | `100` | No |
| `INDEX_REFRESH_INTERVAL` | Index refresh interval | `1s` | No |
| `INDEX_MAX_CONTENT_LENGTH` | Max document content length | `1000000` | No |

## Observability

### Logging

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `LOG_LEVEL` | Application log level | `INFO` | No |
| `LOG_FORMAT` | Log format (json/text) | `json` | No |

### Sentry (Error Tracking)

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `SENTRY_DSN` | Sentry DSN | - | No |
| `SENTRY_ENVIRONMENT` | Sentry environment name | `production` | No |
| `SENTRY_TRACES_SAMPLE_RATE` | Transaction sampling rate | `0.1` | No |

## Example Configurations

### Development

```bash
# Core
DJANGO_DEBUG=true
DJANGO_SECRET_KEY=dev-secret-key-not-for-production

# Database
POSTGRES_HOST=localhost
POSTGRES_PORT=25432
POSTGRES_DB=find
POSTGRES_USER=find
POSTGRES_PASSWORD=find

# Redis
REDIS_URL=redis://localhost:6379/0

# Search (OpenSearch)
SEARCH_BACKEND=opensearch
OPENSEARCH_HOST=localhost
OPENSEARCH_PORT=9200

# OIDC (local Keycloak)
OIDC_OP_ISSUER=http://localhost:8080/realms/find
OIDC_RP_CLIENT_ID=find
OIDC_RP_CLIENT_SECRET=dev-secret
```

### Production

```bash
# Core
DJANGO_DEBUG=false
DJANGO_SECRET_KEY=<64-char-random-string>
DJANGO_ALLOWED_HOSTS=find.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://find.example.com

# Database
POSTGRES_HOST=postgres.internal
POSTGRES_PORT=5432
POSTGRES_DB=find
POSTGRES_USER=find
POSTGRES_PASSWORD=<secure-password>

# Redis
REDIS_URL=redis://redis.internal:6379/0

# Search (OpenSearch with SSL)
SEARCH_BACKEND=opensearch
OPENSEARCH_HOST=opensearch.internal
OPENSEARCH_PORT=9200
OPENSEARCH_USE_SSL=true
OPENSEARCH_USER=find
OPENSEARCH_PASSWORD=<secure-password>

# OIDC
OIDC_OP_ISSUER=https://auth.example.com/realms/main
OIDC_RP_CLIENT_ID=find
OIDC_RP_CLIENT_SECRET=<client-secret>

# Observability
LOG_LEVEL=INFO
LOG_FORMAT=json
SENTRY_DSN=https://xxx@sentry.io/123
SENTRY_ENVIRONMENT=production
```

### Using TypeSense

```bash
SEARCH_BACKEND=typesense
TYPESENSE_HOST=typesense.internal
TYPESENSE_PORT=8108
TYPESENSE_PROTOCOL=https
TYPESENSE_API_KEY=<api-key>
```

### Using Meilisearch

```bash
SEARCH_BACKEND=meilisearch
MEILISEARCH_HOST=meilisearch.internal
MEILISEARCH_PORT=7700
MEILISEARCH_PROTOCOL=https
MEILISEARCH_API_KEY=<master-key>
```

## Related Documentation

- [Setup Guide](setup-indexer.md) - Installation and deployment
- [Architecture](architecture.md) - System design
- [Core Concepts](concepts.md) - Unified index, claims, abstraction
