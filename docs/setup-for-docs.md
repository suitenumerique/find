# Integrating Docs with Find

This guide explains how to integrate the Docs application with Find for document search.

## Overview

Docs uses Find to:
- Index document content for full-text search
- Search across documents with access control
- Keep search index synchronized with document changes

## Prerequisites

- Find service running and accessible
- Docs service registered in Find
- OIDC provider configured for both services

## Service Registration

### 1. Register Docs in Find

Create a service entry for Docs in Find:

```bash
# Via Find management command
python manage.py create_service \
  --name docs \
  --client-id docs-oidc-client-id

# Output:
# Service 'docs' created successfully
# Token: 8f3a9b2c4d5e6f7g8h9i0j1k2l3m4n5o6p7q8r9s0t1u2v3w4x
```

**Save the token securely** - it's required for Docs to authenticate with Find.

### 2. Configure Docs

Add Find configuration to Docs environment:

```bash
# Find API endpoint
FIND_API_URL=https://find.example.com/api/v1.0

# Service token from registration
FIND_SERVICE_TOKEN=8f3a9b2c4d5e6f7g8h9i0j1k2l3m4n5o6p7q8r9s0t1u2v3w4x
```

## Indexing Documents

### Document Schema

When indexing a document, Docs sends:

```json
{
  "id": "doc-uuid-123",
  "title": "Meeting Notes - Q1 Planning",
  "content": "Full document text content...",
  "path": "/team/planning",
  "depth": 2,
  "tags": ["meeting", "planning", "q1"],
  "users": ["user-sub-alice", "user-sub-bob"],
  "groups": ["planning-team"],
  "reach": "restricted",
  "created_at": "2025-01-15T10:00:00Z",
  "updated_at": "2025-01-15T14:30:00Z"
}
```

### Index API Call

```python
import requests

def index_document(document):
    response = requests.post(
        f"{FIND_API_URL}/documents/index/",
        headers={
            "Authorization": f"Token {FIND_SERVICE_TOKEN}",
            "Content-Type": "application/json"
        },
        json={
            "id": str(document.id),
            "title": document.title,
            "content": document.get_text_content(),
            "path": document.path,
            "depth": document.depth,
            "tags": list(document.tags.values_list("name", flat=True)),
            "users": document.get_user_subs(),
            "groups": document.get_group_slugs(),
            "reach": document.visibility,
            "created_at": document.created_at.isoformat(),
            "updated_at": document.updated_at.isoformat()
        }
    )
    response.raise_for_status()
    return response.json()
```

### Bulk Indexing

For initial sync or large updates:

```python
def bulk_index_documents(documents):
    response = requests.post(
        f"{FIND_API_URL}/documents/index/bulk/",
        headers={
            "Authorization": f"Token {FIND_SERVICE_TOKEN}",
            "Content-Type": "application/json"
        },
        json={
            "documents": [
                {
                    "id": str(doc.id),
                    "title": doc.title,
                    "content": doc.get_text_content(),
                    # ... other fields
                }
                for doc in documents
            ]
        }
    )
    response.raise_for_status()
    return response.json()
```

## Searching Documents

### Search Flow

1. User enters search query in Docs UI
2. Docs forwards request to Find with user's OIDC token
3. Find filters results based on user's access claims
4. Docs displays filtered results

### Search API Call

```python
def search_documents(query, user_token, filters=None):
    response = requests.post(
        f"{FIND_API_URL}/documents/search/",
        headers={
            "Authorization": f"Bearer {user_token}",
            "Content-Type": "application/json"
        },
        json={
            "query": query,
            "filters": filters or {},
            "page": 1,
            "page_size": 20
        }
    )
    response.raise_for_status()
    return response.json()
```

### Search Response

```json
{
  "count": 42,
  "results": [
    {
      "id": "doc-uuid-123",
      "title": "Meeting Notes - Q1 Planning",
      "highlight": {
        "content": ["...discussed <em>Q1 planning</em> objectives..."]
      },
      "score": 12.5
    }
  ],
  "page": 1,
  "page_size": 20
}
```

## Access Control

### Setting Document Permissions

Map Docs permissions to Find access control fields:

| Docs Permission | Find Field | Value |
|-----------------|------------|-------|
| Owner | `users` | Owner's SUB |
| Shared users | `users` | List of user SUBs |
| Shared groups | `groups` | List of group slugs |
| Public | `reach` | `"public"` |
| Team only | `reach` | `"authenticated"` |
| Private | `reach` | `"restricted"` |

### Example: Shared Document

```python
def get_access_control(document):
    users = [document.owner.sub]
    groups = []
    reach = "restricted"
    
    for share in document.shares.all():
        if share.share_type == "user":
            users.append(share.target_user.sub)
        elif share.share_type == "group":
            groups.append(share.target_group.slug)
    
    if document.is_public:
        reach = "public"
    elif document.is_team_visible:
        reach = "authenticated"
    
    return {
        "users": users,
        "groups": groups,
        "reach": reach
    }
```

## Synchronization

### Real-time Sync

Index documents on create/update:

```python
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

@receiver(post_save, sender=Document)
def index_on_save(sender, instance, **kwargs):
    # Queue async indexing task
    index_document_task.delay(instance.id)

@receiver(post_delete, sender=Document)
def delete_on_remove(sender, instance, **kwargs):
    delete_document_task.delay(instance.id)
```

### Batch Sync

Periodic full sync for consistency:

```python
from celery import shared_task

@shared_task
def full_sync():
    documents = Document.objects.filter(is_active=True)
    for batch in chunked(documents, 100):
        bulk_index_documents(batch)
```

## Deleting Documents

### Single Document

```python
def delete_document(document_id):
    response = requests.delete(
        f"{FIND_API_URL}/documents/{document_id}/",
        headers={
            "Authorization": f"Token {FIND_SERVICE_TOKEN}"
        }
    )
    response.raise_for_status()
```

### By Tags

```python
def delete_by_tags(tags):
    response = requests.post(
        f"{FIND_API_URL}/documents/delete/",
        headers={
            "Authorization": f"Token {FIND_SERVICE_TOKEN}",
            "Content-Type": "application/json"
        },
        json={"tags": tags}
    )
    response.raise_for_status()
```

## Error Handling

### Retry Logic

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10)
)
def index_with_retry(document):
    return index_document(document)
```

### Error Responses

| Status | Meaning | Action |
|--------|---------|--------|
| 400 | Invalid document schema | Fix document data |
| 401 | Invalid service token | Check FIND_SERVICE_TOKEN |
| 404 | Document not found (delete) | Already deleted, ignore |
| 503 | Find unavailable | Retry with backoff |

## Monitoring

### Health Check

```python
def check_find_health():
    response = requests.get(f"{FIND_API_URL}/health/")
    return response.status_code == 200
```

### Metrics to Track

- Index latency (p95, p99)
- Search latency (p95, p99)
- Index error rate
- Search error rate
- Documents indexed per minute

## Related Documentation

- [Core Concepts](concepts.md) - Unified index, claims, abstraction
- [Setup Guide](setup-indexer.md) - Find configuration
- [Environment Variables](env.md) - Configuration reference
