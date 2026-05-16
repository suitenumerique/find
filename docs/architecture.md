## Architecture

### Global system architecture

```mermaid
flowchart TD
    Docs -- REST API --> Back("Backend (Django)")
    Back --> DB("Database (PostgreSQL)")
    Back -- REST API --> Opensearch
    Back <--> Celery --> DB
    User -- HTTP --> Dashboard --> Opensearch
    Back -- REST API --> Embedding Endpoint
```

### Search Access Control

Find implements a layered access control system for document search that combines **system scope** (server-enforced) with **user scope** (client-provided filters).

#### Document Reach Levels

Documents have a `reach` field with three possible values:

| Reach | Description |
|-------|-------------|
| `public` | Visible to anyone |
| `authenticated` | Visible to any authenticated user |
| `restricted` | Visible only to users in the document's `users` array |

#### Authentication Types

The `/api/v1.0/documents/search` endpoint accepts two authentication methods:

| Auth Type | Token | Use Case |
|-----------|-------|----------|
| **Service** | Service API token | Service-to-service calls (e.g., from Docs application) |
| **OIDC** | User's OIDC bearer token | Direct user access |

#### System Scope vs User Scope

```
┌─────────────────────────────────────────────────────────────────┐
│                        Final Query Filter                        │
│                                                                  │
│   ┌──────────────────────┐    AND    ┌──────────────────────┐   │
│   │     System Scope     │           │     User Scope       │   │
│   │   (server-enforced)  │           │  (client `where`)    │   │
│   └──────────────────────┘           └──────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**System Scope** is constructed by `build_system_scope()` and always includes:
- `is_active = true` (only active documents)
- `service = <authenticated_service>` (if service auth)
- For OIDC users: `(reach != restricted) OR (user_sub IN users)`

**User Scope** is the optional `where` clause from the API request body.

#### How They Combine

The system scope and user scope are combined with AND logic:

```python
final_filter = user_where AND system_scope
```

This means:
1. **System scope cannot be bypassed** - it's always enforced
2. **User scope can only narrow results** - never widen them
3. **OIDC users get automatic access control** based on their identity

#### Authentication Flow

```
┌─────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│   Request   │────▶│  SearchAuthMiddleware │────▶│    Handler      │
└─────────────┘     └──────────────────────┘     └─────────────────┘
                              │                           │
                    ┌─────────┴─────────┐                 │
                    ▼                   ▼                 │
              Service Token?      OIDC Token?            │
                    │                   │                 │
                    ▼                   ▼                 │
              auth_type=service   auth_type=oidc         │
              service_name=X      user.sub=Y             │
                    │                   │                 │
                    └─────────┬─────────┘                 │
                              ▼                           │
                    ┌─────────────────────┐              │
                    │  combine_with_      │◀─────────────┘
                    │  system_scope()     │
                    └─────────────────────┘
                              │
                              ▼
                    ┌─────────────────────┐
                    │  OpenSearch Query   │
                    └─────────────────────┘
```

#### Examples

**OIDC User Search (user_sub=alice@example.com)**

System scope automatically injected:
```json
{
  "and": [
    {"field": "is_active", "op": "eq", "value": true},
    {
      "or": [
        {"not": {"field": "reach", "op": "eq", "value": "restricted"}},
        {"field": "users", "op": "in", "value": ["alice@example.com"]}
      ]
    }
  ]
}
```

Result: Alice sees public docs, authenticated docs, and restricted docs where she's listed.

**Service Token Search (service=docs)**

System scope:
```json
{
  "and": [
    {"field": "is_active", "op": "eq", "value": true},
    {"field": "service", "op": "eq", "value": "docs"}
  ]
}
```

Result: Service sees all active documents it owns. Access control is the service's responsibility.

**OIDC User with Additional Filter**

User request:
```json
{
  "query": "meeting notes",
  "where": {"field": "tags", "op": "in", "value": ["meetings"]}
}
```

Final filter combines both:
```json
{
  "and": [
    {"field": "tags", "op": "in", "value": ["meetings"]},
    {
      "and": [
        {"field": "is_active", "op": "eq", "value": true},
        {
          "or": [
            {"not": {"field": "reach", "op": "eq", "value": "restricted"}},
            {"field": "users", "op": "in", "value": ["alice@example.com"]}
          ]
        }
      ]
    }
  ]
}
```

Result: Alice sees meeting-tagged documents that she has access to. She cannot bypass the access control by omitting or modifying the system scope.

#### Query DSL Reference

For complete documentation of the search query syntax, operators, and examples, see [SEARCH_QUERY_SCHEMA.md](./SEARCH_QUERY_SCHEMA.md).
