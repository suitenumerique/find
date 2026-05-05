# Integrating Drive with Find

This guide explains how to integrate the Drive application with Find for file search.

## Overview

Drive uses Find to:
- Index file metadata and content for full-text search
- Search across files with folder-based access control
- Keep search index synchronized with file changes

## Prerequisites

- Find service running and accessible
- Drive service registered in Find
- OIDC provider configured for both services

## Service Registration

### 1. Register Drive in Find

Create a service entry for Drive in Find:

```bash
# Via Find management command
python manage.py create_service \
  --name drive \
  --client-id drive-oidc-client-id

# Output:
# Service 'drive' created successfully
# Token: 9g4b0c3d5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z
```

**Save the token securely** - it's required for Drive to authenticate with Find.

### 2. Configure Drive

Add Find configuration to Drive environment:

```bash
# Find API endpoint
FIND_API_URL=https://find.example.com/api/v1.0

# Service token from registration
FIND_SERVICE_TOKEN=9g4b0c3d5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z
```

## Indexing Files

### File Schema

When indexing a file, Drive sends:

```json
{
  "id": "file-uuid-456",
  "title": "Q1 Financial Report.pdf",
  "content": "Extracted text content from PDF...",
  "path": "/Finance/Reports/2025",
  "depth": 3,
  "size": 2048576,
  "tags": ["finance", "report", "q1"],
  "users": ["user-sub-charlie"],
  "groups": ["finance-team"],
  "reach": "restricted",
  "created_at": "2025-01-20T09:00:00Z",
  "updated_at": "2025-01-20T09:00:00Z"
}
```

### Content Extraction

Extract searchable text from files before indexing:

```python
def extract_content(file):
    """Extract text content based on file type."""
    if file.mime_type == "application/pdf":
        return extract_pdf_text(file.path)
    elif file.mime_type in ["application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]:
        return extract_docx_text(file.path)
    elif file.mime_type.startswith("text/"):
        return file.read_text()
    else:
        # Non-text files: index metadata only
        return ""
```

### Index API Call

```python
import requests

def index_file(file):
    response = requests.post(
        f"{FIND_API_URL}/documents/index/",
        headers={
            "Authorization": f"Token {FIND_SERVICE_TOKEN}",
            "Content-Type": "application/json"
        },
        json={
            "id": str(file.id),
            "title": file.name,
            "content": extract_content(file),
            "path": file.folder_path,
            "depth": file.depth,
            "size": file.size,
            "tags": list(file.tags.values_list("name", flat=True)),
            "users": file.get_user_subs(),
            "groups": file.get_group_slugs(),
            "reach": file.visibility,
            "created_at": file.created_at.isoformat(),
            "updated_at": file.updated_at.isoformat()
        }
    )
    response.raise_for_status()
    return response.json()
```

### Bulk Indexing

For initial sync or folder moves:

```python
def bulk_index_files(files):
    response = requests.post(
        f"{FIND_API_URL}/documents/index/bulk/",
        headers={
            "Authorization": f"Token {FIND_SERVICE_TOKEN}",
            "Content-Type": "application/json"
        },
        json={
            "documents": [
                {
                    "id": str(f.id),
                    "title": f.name,
                    "content": extract_content(f),
                    # ... other fields
                }
                for f in files
            ]
        }
    )
    response.raise_for_status()
    return response.json()
```

## Searching Files

### Search Flow

1. User enters search query in Drive UI
2. Drive forwards request to Find with user's OIDC token
3. Find filters results based on user's access claims
4. Drive displays filtered results with file icons and paths

### Search API Call

```python
def search_files(query, user_token, folder_path=None):
    filters = {}
    if folder_path:
        filters["path_prefix"] = folder_path
    
    response = requests.post(
        f"{FIND_API_URL}/documents/search/",
        headers={
            "Authorization": f"Bearer {user_token}",
            "Content-Type": "application/json"
        },
        json={
            "query": query,
            "filters": filters,
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
  "count": 15,
  "results": [
    {
      "id": "file-uuid-456",
      "title": "Q1 Financial Report.pdf",
      "path": "/Finance/Reports/2025",
      "highlight": {
        "content": ["...revenue increased by <em>15%</em> in Q1..."]
      },
      "score": 8.2
    }
  ],
  "page": 1,
  "page_size": 20
}
```

## Access Control

### Folder-Based Permissions

Drive uses folder hierarchy for permissions. Map to Find access control:

```python
def get_access_control(file):
    """
    Collect permissions from file and parent folders.
    Users/groups with access to parent folder have access to file.
    """
    users = set()
    groups = set()
    
    # File owner always has access
    users.add(file.owner.sub)
    
    # Direct file shares
    for share in file.shares.all():
        if share.share_type == "user":
            users.add(share.target_user.sub)
        elif share.share_type == "group":
            groups.add(share.target_group.slug)
    
    # Inherited folder permissions
    folder = file.parent_folder
    while folder:
        for share in folder.shares.all():
            if share.share_type == "user":
                users.add(share.target_user.sub)
            elif share.share_type == "group":
                groups.add(share.target_group.slug)
        folder = folder.parent_folder
    
    # Determine reach level
    if file.is_public or any(f.is_public for f in file.ancestor_folders):
        reach = "public"
    elif file.is_team_visible:
        reach = "authenticated"
    else:
        reach = "restricted"
    
    return {
        "users": list(users),
        "groups": list(groups),
        "reach": reach
    }
```

### Permission Changes

When folder permissions change, reindex all contained files:

```python
def on_folder_permission_change(folder):
    """Reindex all files in folder and subfolders."""
    files = File.objects.filter(
        path__startswith=folder.path
    ).select_related("owner")
    
    bulk_index_files(files)
```

## Synchronization

### Real-time Sync

Index files on create/update/move:

```python
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

@receiver(post_save, sender=File)
def index_on_save(sender, instance, **kwargs):
    index_file_task.delay(instance.id)

@receiver(post_delete, sender=File)
def delete_on_remove(sender, instance, **kwargs):
    delete_file_task.delay(instance.id)
```

### File Move Handling

When files move between folders:

```python
def on_file_move(file, old_path, new_path):
    """
    Reindex file with new path and permissions.
    Permissions may change based on new parent folder.
    """
    index_file(file)
```

### Folder Move Handling

When folders move, reindex all contents:

```python
def on_folder_move(folder, old_path, new_path):
    """Reindex all files in moved folder."""
    files = File.objects.filter(path__startswith=new_path)
    bulk_index_files(files)
```

## Large File Handling

### Content Size Limits

For large files, truncate content:

```python
MAX_CONTENT_LENGTH = 1_000_000  # 1MB

def extract_content_safe(file):
    content = extract_content(file)
    if len(content) > MAX_CONTENT_LENGTH:
        content = content[:MAX_CONTENT_LENGTH]
    return content
```

### Async Content Extraction

Extract content asynchronously for large files:

```python
from celery import shared_task

@shared_task
def extract_and_index(file_id):
    file = File.objects.get(id=file_id)
    content = extract_content(file)
    index_file(file, content=content)
```

## Deleting Files

### Single File

```python
def delete_file_from_index(file_id):
    response = requests.delete(
        f"{FIND_API_URL}/documents/{file_id}/",
        headers={
            "Authorization": f"Token {FIND_SERVICE_TOKEN}"
        }
    )
    if response.status_code != 404:
        response.raise_for_status()
```

### Folder Deletion

When deleting a folder, delete all contained files:

```python
def delete_folder_from_index(folder_path):
    """Delete all files under a folder path."""
    response = requests.post(
        f"{FIND_API_URL}/documents/delete/",
        headers={
            "Authorization": f"Token {FIND_SERVICE_TOKEN}",
            "Content-Type": "application/json"
        },
        json={"path_prefix": folder_path}
    )
    response.raise_for_status()
```

## Error Handling

### Content Extraction Errors

```python
def safe_extract_content(file):
    try:
        return extract_content(file)
    except Exception as e:
        logger.warning(f"Content extraction failed for {file.id}: {e}")
        return ""  # Index with metadata only
```

### Retry Logic

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10)
)
def index_with_retry(file):
    return index_file(file)
```

## Monitoring

### Health Check

```python
def check_find_health():
    response = requests.get(f"{FIND_API_URL}/health/")
    return response.status_code == 200
```

### Metrics to Track

- Index latency by file type
- Content extraction time
- Search latency (p95, p99)
- Index error rate by file type
- Files indexed per minute

## Related Documentation

- [Core Concepts](concepts.md) - Unified index, claims, abstraction
- [Setup Guide](setup-indexer.md) - Find configuration
- [Environment Variables](env.md) - Configuration reference
