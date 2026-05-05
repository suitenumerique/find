# Find

**Federated document search for OIDC-connected applications.**

Find provides a unified search API that enables applications in an OIDC federation to index and search documents with proper access control. It abstracts the underlying search engine, allowing you to choose the backend that best fits your needs.

## Key Features

- **Unified Index**: All documents stored in a single index, isolated by service
- **Access Control**: Fine-grained permissions via users, groups, and reach levels
- **Search Abstraction**: Swap search backends without changing application code
- **OIDC Integration**: Seamless authentication with your identity provider

## How It Works

```
┌─────────────────────────────────────────────────────────────┐
│                    Applications                              │
│              (Docs, Drive, Messaging)                        │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                         Find                                 │
│         • Index documents with access control                │
│         • Search with automatic permission filtering         │
│         • Backend-agnostic API                              │
└──────────────────────────┬──────────────────────────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
    ┌─────────┐      ┌──────────┐      ┌───────────┐
    │OpenSearch│      │TypeSense │      │Meilisearch│
    └─────────┘      └──────────┘      └───────────┘
```

## Quick Start

```bash
# Clone and setup
git clone https://github.com/suitenumerique/find.git
cd find
cp env.d/development/common.dist.env env.d/development/common.env

# Start services
make bootstrap
make migrate
make create-index

# Find is running at http://localhost:8081
```

## API Overview

### Index a Document

```bash
curl -X POST http://localhost:8081/api/v1.0/documents/index/ \
  -H "Authorization: Token YOUR_SERVICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "doc-123",
    "title": "Project Roadmap",
    "content": "Q1 objectives and milestones...",
    "users": ["user-sub-1"],
    "groups": ["engineering"],
    "reach": "restricted"
  }'
```

### Search Documents

```bash
curl -X POST http://localhost:8081/api/v1.0/documents/search/ \
  -H "Authorization: Bearer OIDC_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "roadmap"
  }'
```

## Supported Search Backends

| Backend | Best For |
|---------|----------|
| **OpenSearch** | Large-scale deployments, complex queries |
| **TypeSense** | Low-latency, typo-tolerant search |
| **Meilisearch** | Quick setup, excellent relevance |

Configure via environment variable:

```bash
SEARCH_BACKEND=opensearch  # or typesense, meilisearch
```

## Access Control

Documents are protected by claims set during indexation:

| Field | Description |
|-------|-------------|
| `users` | List of user SUBs who can access |
| `groups` | List of group slugs who can access |
| `reach` | `public`, `authenticated`, or `restricted` |

Find automatically filters search results based on the authenticated user's identity and group memberships.

## Documentation

- [Core Concepts](docs/concepts.md) - Unified index, claims, search abstraction
- [Architecture](docs/architecture.md) - System design and data flow
- [Setup Guide](docs/setup-indexer.md) - Installation and configuration
- [Environment Variables](docs/env.md) - Complete configuration reference
- [Docs Integration](docs/setup-for-docs.md) - Integrate with Docs
- [Drive Integration](docs/setup-for-drive.md) - Integrate with Drive

## Tech Stack

- **Backend**: Django 6.0, Django REST Framework
- **Search**: OpenSearch / TypeSense / Meilisearch
- **Database**: PostgreSQL
- **Queue**: Celery + Redis
- **Auth**: OIDC (Mozilla Django OIDC)

## Development

```bash
# Run tests
make test

# Code quality
make lint
make format

# Build Docker image
make build
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions welcome! Please read our contributing guidelines before submitting PRs.
