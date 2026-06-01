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

### Per-service index topology

Each registered service gets its own OpenSearch index. The index name is derived from the
`OPENSEARCH_INDEX_PREFIX` setting and the service's name:

```
{OPENSEARCH_INDEX_PREFIX}-{service.name}
```

```
Services (bearer token auth)          OpenSearch
+------------------+                  +------------------+
| docs service     | -- /index/ -->   | find-docs        |
+------------------+                  +------------------+
| drive service    | -- /index/ -->   | find-drive       |
+------------------+                  +------------------+
| wiki service     | -- /index/ -->   | find-wiki        |
+------------------+                  +------------------+
                                              |
                                              | fan-out across
                                              | all active indices
                                              |
Users (OIDC token auth)                       v
+------------------+                  +------------------+
| OIDC user        | -- /search/ -->  | find-docs        |
|                  |                  | find-drive       |
|                  | -- /delete/ -->  | find-wiki        |
+------------------+                  +------------------+
```

**Services cannot search. Only users (OIDC tokens) can search and delete.**

- `/index/` accepts service bearer tokens (`ServiceTokenAuthentication`). Each service writes
  exclusively to its own index.
- `/search/` and `/delete/` accept OIDC user tokens (`ResourceServerAuthentication`). Queries
  fan out across all indices belonging to `is_active=True` services.

Setting `Service.is_active=False` removes that service's index from the fan-out. Documents in
that index become invisible to users until the service is re-activated.

See [services-cannot-search.md](./services-cannot-search.md) for the full contract.
