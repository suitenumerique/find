# Find Core Concepts

This document explains the fundamental concepts behind Find's architecture.

## Overview

Find is a **federated document search system** that provides a unified search API across multiple applications in an OIDC federation. It acts as an abstraction layer between applications and the underlying search engine, allowing users to search documents with proper access control.

```
┌─────────────────────────────────────────────────────────────┐
│                    Applications                              │
│         (Docs, Drive, Messaging, etc.)                       │
└──────────────────────────┬──────────────────────────────────┘
                           │ Index & Search API
┌──────────────────────────▼──────────────────────────────────┐
│                         Find                                 │
│    ┌─────────────────────────────────────────────────────┐  │
│    │              Search Abstraction Layer               │  │
│    │         (Backend-agnostic interface)                │  │
│    └─────────────────────────────────────────────────────┘  │
│                           │                                  │
│         ┌─────────────────┼─────────────────┐               │
│         ▼                 ▼                 ▼               │
│    ┌─────────┐      ┌──────────┐      ┌───────────┐        │
│    │OpenSearch│      │TypeSense │      │Meilisearch│        │
│    └─────────┘      └──────────┘      └───────────┘        │
└─────────────────────────────────────────────────────────────┘
```

## Unified Index

All documents from all services are stored in a **single unified index**. Each document contains a `service` field that identifies which application indexed it.

### Why Unified Index?

- **Simplified operations**: One index to manage, backup, and scale
- **Cross-service potential**: Foundation for future cross-application search
- **Consistent schema**: All documents share the same field mappings
- **Easier migrations**: Switch search backends without per-service complexity

### Document Structure

Every document in the unified index contains:

```json
{
  "id": "uuid",
  "service": "docs",           // Which service owns this document
  "title": "Document title",
  "content": "Full text content",
  "created_at": "2025-01-01T00:00:00Z",
  "updated_at": "2025-01-01T00:00:00Z",
  "size": 1024,
  
  // Access control (set by the indexing service)
  "users": ["user-sub-1", "user-sub-2"],
  "groups": ["group-slug-1"],
  "reach": "restricted",
  
  // Metadata
  "tags": ["tag1", "tag2"],
  "path": "/folder/subfolder",
  "depth": 2,
  "numchild": 0,
  "is_active": true
}
```

## Service Claims

A **service** is an application registered with Find (e.g., Docs, Drive). Each service has **claims** over documents it indexes.

### Service Write Claims

Services authenticate using a secure token and can:

- **Index** documents with their service identifier
- **Update** documents they previously indexed
- **Delete** documents they own

A service **cannot** modify documents indexed by another service.

### Service Read Claims

By default, a service can only search documents it has indexed. This ensures:

- **Data isolation**: Each application's documents remain separate
- **Clear ownership**: No confusion about document provenance
- **Security by default**: No accidental data leakage between services

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│    Docs     │     │    Drive    │     │  Messaging  │
│   Service   │     │   Service   │     │   Service   │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       │ Index/Search      │ Index/Search      │ Index/Search
       │ own docs only     │ own docs only     │ own docs only
       │                   │                   │
       ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────┐
│                    Unified Index                         │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────┐   │
│  │service:docs │ │service:drive│ │service:messaging│   │
│  │ documents   │ │ documents   │ │   documents     │   │
│  └─────────────┘ └─────────────┘ └─────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

## User Read Claims

Users don't interact with Find directly - they use their application (Docs, Drive, etc.). When a user searches, Find determines what they can see based on **read claims** set during document indexation.

### How Read Claims Work

When a service indexes a document, it specifies who can read it:

| Field | Purpose |
|-------|---------|
| `users` | List of user SUBs (OIDC subject identifiers) who can access |
| `groups` | List of group slugs who can access |
| `reach` | Visibility level: `public`, `authenticated`, or `restricted` |

### Reach Levels

| Reach | Who Can See |
|-------|------------|
| `public` | Anyone (no authentication required) |
| `authenticated` | Any authenticated user in the federation |
| `restricted` | Only users listed in `users` or `groups` fields |

### Search Access Control

When a user searches, Find filters results based on:

1. The user's OIDC `sub` (subject) claim
2. The user's group memberships
3. Document visibility (reach level)
4. Documents the user has explicitly visited (for public/authenticated reach)

```
User Search Request
       │
       ▼
┌─────────────────────────────────────┐
│        Access Control Filter         │
│                                      │
│  Document is visible if:             │
│                                      │
│  (reach != restricted AND visited)   │
│           OR                         │
│  (user.sub IN document.users)        │
│           OR                         │
│  (user.groups ∩ document.groups)     │
│                                      │
└─────────────────────────────────────┘
       │
       ▼
   Filtered Results
```

## Search Abstraction Layer

Find provides a **backend-agnostic search API**. Applications interact with Find's REST API without knowing which search engine is used underneath.

### Supported Backends

Find supports multiple search backends:

| Backend | Best For |
|---------|----------|
| **OpenSearch** | Large-scale deployments, complex queries, existing Elasticsearch expertise |
| **TypeSense** | Low-latency searches, typo tolerance, simpler operations |
| **Meilisearch** | Fast setup, excellent relevance, developer-friendly |

### API Agnosticism

The Find API is completely agnostic to the backend:

- **Same endpoints** regardless of backend
- **Same request/response format**
- **Same query syntax**
- **Same access control behavior**

Applications don't need to change when you switch backends. This enables:

- **Backend migrations** without application changes
- **A/B testing** different search engines
- **Environment flexibility** (e.g., Meilisearch for dev, OpenSearch for prod)

### Configuration

The backend is selected via environment variable:

```bash
SEARCH_BACKEND=opensearch  # or typesense, meilisearch
```

Each backend has its own configuration section. See [Environment Variables](env.md) for details.

## Summary

| Concept | Description |
|---------|-------------|
| **Unified Index** | Single index for all documents, identified by `service` field |
| **Service Write Claims** | Services can only modify their own documents |
| **Service Read Claims** | Services can only search their own documents |
| **User Read Claims** | Access determined by `users`, `groups`, and `reach` fields |
| **Search Abstraction** | Backend-agnostic API supporting multiple search engines |

## Next Steps

- [Architecture Overview](architecture.md) - System architecture and data flow
- [Setting Up Find](setup-indexer.md) - Configuration and deployment
- [Environment Variables](env.md) - Complete configuration reference
