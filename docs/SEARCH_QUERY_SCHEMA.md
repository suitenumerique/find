# Find Search Query Schema

Find provides a powerful, flexible query DSL for searching documents with complex filtering, sorting, and access control.

## Architecture Overview

Find is a **federated search service** that indexes documents from multiple applications (services) sharing a common OIDC federation. It supports two authentication modes:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Find Search API                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────┐       ┌─────────────────────────────────────┐  │
│  │    OIDC Token Auth      │       │       Service Token Auth            │  │
│  │   (End-User Search)     │       │    (Service-to-Service)             │  │
│  ├─────────────────────────┤       ├─────────────────────────────────────┤  │
│  │ • User's access token   │       │ • Service API key                   │  │
│  │ • user_sub extracted    │       │ • Service name identified           │  │
│  │ • Auto user filtering   │       │ • Full service access               │  │
│  │ • (reach!=restricted)   │       │ • Client controls filtering         │  │
│  │   OR (user in users)    │       │ • Service enforces own ACL          │  │
│  └─────────────────────────┘       └─────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Design Principles

1. **Service tokens = Full service access**: Service tokens represent the service itself, not a user. Services have unrestricted access to their own documents.

2. **User filtering is service responsibility**: When using service tokens, the calling service must implement user-level access control via the `where` clause.

3. **OIDC tokens = Automatic user filtering**: When users authenticate directly, Find automatically enforces access control based on `reach` and `users` fields.

4. **Separation of concerns**: Find handles search/ranking; calling services handle business logic and user authorization.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Quick Start](#quick-start)
- [API Endpoint](#api-endpoint)
- [Request Schema](#request-schema)
- [Where Clause DSL](#where-clause-dsl)
- [Operators](#operators)
- [Fields](#fields)
- [Sort Clause](#sort-clause)
- [Access Control](#access-control)
- [Service Integration Pattern](#service-integration-pattern)
- [Examples](#examples)

---

## Quick Start

```bash
# Simple search
curl -X POST "http://localhost:8081/api/v1.0/documents/search" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"query": "meeting notes", "limit": 10}'

# Search with filters
curl -X POST "http://localhost:8081/api/v1.0/documents/search" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "project",
    "where": {
      "and": [
        {"field": "tags", "op": "in", "value": ["important", "urgent"]},
        {"field": "reach", "op": "eq", "value": "public"}
      ]
    },
    "sort": [{"field": "updated_at", "direction": "desc"}],
    "limit": 20
  }'
```

---

## API Endpoint

```
POST /api/v1.0/documents/search
```

**Authentication**: Bearer token (OIDC or Service token)

---

## Request Schema

```typescript
interface SearchQuerySchema {
  query?: string;              // Full-text search query (optional)
  where?: WhereClause;         // Filter conditions (optional)
  sort?: SortClause[];         // Sort specifications (optional)
  limit?: number;              // Results limit: 1-100 (default: 50)
}
```

### Response Schema

```typescript
interface SearchResponse {
  data: SearchResultDocument[];  // Array of matching documents
  total: number;                 // Total number of matches
  limit: number;                 // Applied limit
}

interface SearchResultDocument {
  id: string;
  title: string;
  content: string;
  size: number;
  depth: number;
  path: string;
  numchild: number;
  created_at: string;           // ISO 8601 datetime
  updated_at: string;           // ISO 8601 datetime
  reach: string | null;         // "public" | "authenticated" | "restricted"
  tags: string[];
  number_of_users: number;      // Count of users with access
  number_of_groups: number;     // Count of groups with access
}
```

---

## Where Clause DSL

The `where` clause supports a recursive boolean expression tree with four node types:

### 1. Field Condition (Leaf Node)

```json
{
  "field": "<field_name>",
  "op": "<operator>",
  "value": <value>
}
```

### 2. AND Clause

```json
{
  "and": [
    <where_clause>,
    <where_clause>,
    ...
  ]
}
```

### 3. OR Clause

```json
{
  "or": [
    <where_clause>,
    <where_clause>,
    ...
  ]
}
```

### 4. NOT Clause

```json
{
  "not": <where_clause>
}
```

### Nesting

Clauses can be nested arbitrarily deep:

```json
{
  "and": [
    {
      "or": [
        {"field": "reach", "op": "eq", "value": "public"},
        {"field": "reach", "op": "eq", "value": "authenticated"}
      ]
    },
    {
      "not": {"field": "tags", "op": "in", "value": ["draft"]}
    },
    {"field": "is_active", "op": "eq", "value": true}
  ]
}
```

---

## Operators

| Operator | Description | Value Type | Example |
|----------|-------------|------------|---------|
| `eq` | Equals | `string \| int \| float \| bool` | `{"field": "reach", "op": "eq", "value": "public"}` |
| `in` | Value in list (ANY match) | `list[string \| int]` | `{"field": "tags", "op": "in", "value": ["tag1", "tag2"]}` |
| `all` | All values must match | `list[string \| int]` | `{"field": "tags", "op": "all", "value": ["required1", "required2"]}` |
| `prefix` | String prefix match | `string` | `{"field": "path", "op": "prefix", "value": "/docs/"}` |
| `gt` | Greater than | `int \| float` | `{"field": "size", "op": "gt", "value": 1000}` |
| `gte` | Greater than or equal | `int \| float` | `{"field": "depth", "op": "gte", "value": 2}` |
| `lt` | Less than | `int \| float` | `{"field": "size", "op": "lt", "value": 50000}` |
| `lte` | Less than or equal | `int \| float` | `{"field": "numchild", "op": "lte", "value": 10}` |
| `exists` | Field exists/not exists | `bool` | `{"field": "tags", "op": "exists", "value": true}` |

### Operator Details

#### `in` vs `all`

- **`in`**: Document matches if field contains **ANY** of the values (OR logic)
- **`all`**: Document matches if field contains **ALL** of the values (AND logic)

```json
// Match documents with tag1 OR tag2
{"field": "tags", "op": "in", "value": ["tag1", "tag2"]}

// Match documents with tag1 AND tag2
{"field": "tags", "op": "all", "value": ["tag1", "tag2"]}
```

#### `exists`

```json
// Documents that HAVE tags
{"field": "tags", "op": "exists", "value": true}

// Documents that DON'T have tags
{"field": "tags", "op": "exists", "value": false}
```

---

## Fields

### User-Queryable Fields

These fields can be used in `where` clauses by API clients:

| Field | Type | Description |
|-------|------|-------------|
| `id` | `string` | Document UUID (mapped to `_id` in OpenSearch) |
| `title` | `string` | Document title |
| `content` | `string` | Document content |
| `depth` | `int` | Tree depth (0 = root) |
| `path` | `string` | Hierarchical path |
| `numchild` | `int` | Number of child documents |
| `created_at` | `datetime` | Creation timestamp |
| `updated_at` | `datetime` | Last update timestamp |
| `size` | `int` | Content size in bytes |
| `reach` | `string` | Access level: `"public"`, `"authenticated"`, `"restricted"` |
| `tags` | `list[string]` | Document tags |

### System Fields (Server-Side Only)

These fields are used internally for access control:

| Field | Type | Description |
|-------|------|-------------|
| `is_active` | `bool` | Document is active (not deleted) |
| `users` | `list[string]` | User subs with explicit access |
| `groups` | `list[string]` | Group slugs with access |
| `service` | `string` | Service that owns the document |

---

## Sort Clause

```typescript
interface SortClause {
  field: "relevance" | "title" | "created_at" | "updated_at" | "size";
  direction: "asc" | "desc";  // default: "desc"
}
```

### Examples

```json
// Sort by relevance (default)
{"sort": [{"field": "relevance", "direction": "desc"}]}

// Sort by newest first
{"sort": [{"field": "updated_at", "direction": "desc"}]}

// Sort by title A-Z
{"sort": [{"field": "title", "direction": "asc"}]}

// Multiple sort criteria
{"sort": [
  {"field": "updated_at", "direction": "desc"},
  {"field": "title", "direction": "asc"}
]}
```

---

## Access Control

Find supports two authentication modes with different access control semantics:

### Authentication Modes

| Mode | Token Type | Use Case | Access Scope |
|------|------------|----------|--------------|
| **OIDC** | User's OIDC access token | End-user search | User-level filtering |
| **Service** | Service API key | Service-to-service calls | Full service access |

### OIDC Token (User Access)

When a user authenticates with their OIDC token, Find extracts `user_sub` from the token and applies user-level access control:

```
System filter: is_active=true AND ((reach != "restricted") OR (user_sub IN users))
```

Users see:
- All `public` documents (anyone can see)
- All `authenticated` documents (any logged-in user can see)
- `restricted` documents **only if** user has explicit access (`user_sub` in `users` list)

### Service Token (Full Service Access)

**By design**, service tokens grant full access to all documents belonging to that service. This is intentional:

```
System filter: is_active=true AND service=<service_name>
```

**Why full access?**
- Service tokens represent the **service itself**, not a user
- Services need unrestricted access to index, search, and manage their documents
- User-level access control is the **service's responsibility**, not Find's

**Service responsibilities:**
- The calling service (e.g., Docs) must enforce its own access control
- Service can pass a `where` clause to filter results by user access
- Find trusts the service to implement appropriate user filtering

**Example: Docs → Find with user filtering**

Docs has user session info. When calling Find, Docs builds a `where` clause:

```json
{
  "query": "meeting notes",
  "where": {
    "or": [
      {"field": "reach", "op": "eq", "value": "public"},
      {"field": "reach", "op": "eq", "value": "authenticated"},
      {"field": "users", "op": "in", "value": ["current-user@example.com"]},
      {"field": "id", "op": "in", "value": ["visited-doc-1", "visited-doc-2"]}
    ]
  }
}
```

This way:
- Find handles the search/ranking
- Docs handles user access control
- Clear separation of concerns

### Combined Filter

The system scope is **AND**ed with any client-provided `where` clause:

```
Final filter: <client_where> AND <system_scope>
```

For OIDC tokens, the system adds user filtering automatically.
For service tokens, the system only filters by service - the client `where` clause controls user access.

---

## Service Integration Pattern

This section describes how services (like Docs) should integrate with Find using service tokens.

### Overview

```
┌──────────────────┐                    ┌──────────────────┐
│                  │  Service Token     │                  │
│   Docs Backend   │ ────────────────►  │   Find API       │
│                  │  + where clause    │                  │
│                  │                    │                  │
│  • Has user      │                    │  • Searches      │
│    session       │                    │    OpenSearch    │
│  • Knows user    │                    │  • Returns       │
│    access rules  │                    │    results       │
│  • Builds where  │                    │  • Trusts        │
│    clause        │                    │    service       │
└──────────────────┘                    └──────────────────┘
```

### Why Services Must Build `where` Clauses

When Docs calls Find with a service token:

1. **Find sees the service**, not the user
2. **Find grants full service access** (all Docs documents)
3. **Docs must filter** by passing user-specific `where` clause

This is the correct architecture because:
- Docs has the user session and knows user permissions
- Docs has business logic (e.g., "visited documents" via LinkTrace)
- Find is a search engine, not an authorization system

### Recommended Where Clause Structure

For a typical user search, Docs should build:

```json
{
  "query": "<user's search term>",
  "where": {
    "or": [
      {"field": "reach", "op": "eq", "value": "public"},
      {"field": "reach", "op": "eq", "value": "authenticated"},
      {"field": "users", "op": "in", "value": ["<user_sub>"]},
      {"field": "id", "op": "in", "value": ["<visited_id_1>", "<visited_id_2>", ...]}
    ]
  },
  "limit": 50
}
```

This returns documents where:
- `reach = "public"` - Anyone can see
- `reach = "authenticated"` - Any logged-in user can see
- `user_sub IN users` - User has explicit access
- `id IN visited_ids` - User has previously accessed (via shared link)

### Implementation Example (Python)

```python
def search_documents(user, query: str, limit: int = 50):
    """Search Find with user-level access control."""
    
    # Get IDs of documents user has visited (via LinkTrace)
    visited_ids = list(
        LinkTrace.objects.filter(user=user)
        .values_list("document_id", flat=True)
    )
    
    # Build access control where clause
    where_clause = {
        "or": [
            {"field": "reach", "op": "eq", "value": "public"},
            {"field": "reach", "op": "eq", "value": "authenticated"},
            {"field": "users", "op": "in", "value": [user.sub]},
        ]
    }
    
    # Add visited IDs if any
    if visited_ids:
        where_clause["or"].append({
            "field": "id", 
            "op": "in", 
            "value": [str(id) for id in visited_ids]
        })
    
    # Call Find API with service token
    response = requests.post(
        settings.FIND_SEARCH_URL,
        json={
            "query": query,
            "where": where_clause,
            "limit": limit,
        },
        headers={"Authorization": f"Bearer {settings.FIND_SERVICE_TOKEN}"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()
```

### Groups/Teams Support

If your service uses group-based access, include groups in the where clause:

```json
{
  "where": {
    "or": [
      {"field": "reach", "op": "eq", "value": "public"},
      {"field": "reach", "op": "eq", "value": "authenticated"},
      {"field": "users", "op": "in", "value": ["<user_sub>"]},
      {"field": "groups", "op": "in", "value": ["<team_1>", "<team_2>"]},
      {"field": "id", "op": "in", "value": ["<visited_ids>"]}
    ]
  }
}
```

### Performance Considerations

1. **Limit visited_ids**: If a user has thousands of visited documents, consider:
   - Limiting to most recent N (e.g., 1000)
   - Using a time window (last 30 days)
   
2. **Cache service token**: Reuse the service token across requests

3. **Use appropriate limits**: Default to 50, max is 100

---

## Examples

### 1. Simple Full-Text Search

```json
{
  "query": "quarterly report",
  "limit": 10
}
```

### 2. Filter by Tags

```json
{
  "query": "meeting",
  "where": {
    "field": "tags",
    "op": "in",
    "value": ["important", "follow-up"]
  }
}
```

### 3. Filter by Multiple Criteria (AND)

```json
{
  "query": "project",
  "where": {
    "and": [
      {"field": "reach", "op": "eq", "value": "public"},
      {"field": "size", "op": "gte", "value": 1000},
      {"field": "tags", "op": "in", "value": ["engineering"]}
    ]
  }
}
```

### 4. Complex OR Logic

```json
{
  "where": {
    "or": [
      {"field": "reach", "op": "eq", "value": "public"},
      {"field": "users", "op": "in", "value": ["user@example.com"]},
      {"field": "id", "op": "in", "value": ["uuid-1", "uuid-2", "uuid-3"]}
    ]
  }
}
```

### 5. Exclude Certain Documents

```json
{
  "query": "report",
  "where": {
    "and": [
      {"field": "tags", "op": "in", "value": ["finance"]},
      {"not": {"field": "tags", "op": "in", "value": ["draft", "archived"]}}
    ]
  }
}
```

### 6. Path-Based Filtering (Subtree)

```json
{
  "query": "notes",
  "where": {
    "field": "path",
    "op": "prefix",
    "value": "0001000200030004"
  }
}
```

### 7. Date Range

```json
{
  "where": {
    "and": [
      {"field": "updated_at", "op": "gte", "value": "2024-01-01T00:00:00Z"},
      {"field": "updated_at", "op": "lt", "value": "2024-07-01T00:00:00Z"}
    ]
  },
  "sort": [{"field": "updated_at", "direction": "desc"}]
}
```

### 8. Documents by ID List (Visited Documents)

```json
{
  "where": {
    "or": [
      {"field": "reach", "op": "eq", "value": "public"},
      {"field": "reach", "op": "eq", "value": "authenticated"},
      {"field": "users", "op": "in", "value": ["current-user@example.com"]},
      {"field": "id", "op": "in", "value": [
        "550e8400-e29b-41d4-a716-446655440001",
        "550e8400-e29b-41d4-a716-446655440002",
        "550e8400-e29b-41d4-a716-446655440003"
      ]}
    ]
  }
}
```

### 9. Large Documents Only

```json
{
  "where": {
    "and": [
      {"field": "size", "op": "gt", "value": 10000},
      {"field": "tags", "op": "exists", "value": true}
    ]
  },
  "sort": [{"field": "size", "direction": "desc"}],
  "limit": 50
}
```

### 10. Service Integration (Docs → Find)

When Docs calls Find with service token, it can pass user-level access control:

```json
{
  "query": "search term",
  "where": {
    "or": [
      {"field": "reach", "op": "eq", "value": "public"},
      {"field": "reach", "op": "eq", "value": "authenticated"},
      {"field": "users", "op": "in", "value": ["user-sub-from-docs"]},
      {"field": "id", "op": "in", "value": ["visited-doc-id-1", "visited-doc-id-2"]}
    ]
  },
  "limit": 50
}
```

This allows Docs to enforce its own access control rules while using Find's search capabilities.

---

## Error Responses

### 401 Unauthorized

Missing or invalid authentication token.

### 422 Validation Error

```json
{
  "detail": [
    {
      "loc": ["body"],
      "msg": "Invalid where clause: {'field': 'tags'}",
      "type": "validation_error"
    }
  ]
}
```

Common validation errors:
- Missing `op` or `value` in field condition
- Invalid operator name
- Invalid field name
- Invalid sort field or direction
- Limit out of range (1-100)

---

## OpenSearch Query Mapping

The DSL is converted to OpenSearch queries:

| DSL | OpenSearch |
|-----|------------|
| `{"and": [...]}` | `{"bool": {"must": [...]}}` |
| `{"or": [...]}` | `{"bool": {"should": [...], "minimum_should_match": 1}}` |
| `{"not": {...}}` | `{"bool": {"must_not": [...]}}` |
| `{"field": "x", "op": "eq", "value": "v"}` | `{"term": {"x": "v"}}` |
| `{"field": "x", "op": "in", "value": [...]}` | `{"terms": {"x": [...]}}` |
| `{"field": "x", "op": "prefix", "value": "v"}` | `{"prefix": {"x": "v"}}` |
| `{"field": "x", "op": "gt", "value": n}` | `{"range": {"x": {"gt": n}}}` |
| `{"field": "x", "op": "exists", "value": true}` | `{"exists": {"field": "x"}}` |

The `id` field is automatically mapped to `_id` for OpenSearch compatibility.
