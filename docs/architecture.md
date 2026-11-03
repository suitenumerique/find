## Architecture

Find indexes the documents of La Suite services (e.g. Docs, Drive) in
OpenSearch and lets their users search them across services. It is an API
called by the services' backends, with no frontend. The decisions behind this
architecture are recorded in [ADR-0001](adr/ADR-0001-20261019-async-django-ninja-and-menshen.md).

### Components

```mermaid
flowchart LR
    subgraph services["La Suite services"]
        Docs
        Drive
    end
    IdP("Identity provider (OIDC)")
    Menshen("Menshen (token exchange)")
    subgraph find["Find"]
        API("API (Django, django-ninja, uvicorn ASGI)")
        Admin("Django admin")
    end
    OpenSearch[("OpenSearch<br>one index per service")]
    PostgreSQL[("PostgreSQL<br>services, admin users")]
    Redis[("Redis<br>cache")]

    Docs & Drive -- "index (service token)" --> API
    Docs & Drive -- "search, delete (exchanged token)" --> API
    Docs & Drive -- "exchange user token" --> Menshen
    Menshen -- "introspect user token" --> IdP
    API -- "introspect exchanged token" --> Menshen
    API --> OpenSearch
    API & Admin --> PostgreSQL
    API & Admin --> Redis
```

- **API**: three async endpoints under `/api/v1.0/documents/` (`index/`,
  `search/`, `delete/`), served by uvicorn workers. Their OpenAPI schema and
  documentation can be enabled with `API_OPENAPI_ENABLED` and
  `API_DOCS_ENABLED`.
- **Admin**: registers the services and gives them their token, and runs the
  self-tests (`/admin/selftest/`). Its static files are served by ServeStatic.
- **OpenSearch** stores the documents, one index per service:
  `{OPENSEARCH_INDEX_PREFIX}-{service name}`.
- **PostgreSQL** stores the registered services, with the hash of their token,
  and the admin users.
- **Redis** is the cache: introspection results and admin sessions.

### Indexing

A service indexes its documents with its service token. It may only write to
its own index.

```mermaid
sequenceDiagram
    participant S as Service (e.g. Docs)
    participant F as Find
    participant P as PostgreSQL
    participant O as OpenSearch
    S->>F: POST /api/v1.0/documents/index/ (service token)<br>a document or a list of documents
    F->>P: look up the active service by token hash
    F->>F: validate the documents (Pydantic),<br>detect their language
    F->>O: create the service's index if needed,<br>index the documents
    F-->>S: 201 / 207 with each document's status,<br>400 if a document is invalid
```

The language of each document is detected (py3langid). Its title and content
are stored in language-specific fields (`title.fr`, `content.en`, …) analyzed
for that language, plus trigram fields that tolerate typos. A bulk request
indexes nothing if any document fails validation.

### Search and delete

Search and delete act on behalf of a user. The service exchanges the user's
access token with Menshen for a token targeting Find, by requesting an action
scope; Menshen grants it as `find:<service>:search` or
`find:<service>:delete` scopes.

```mermaid
sequenceDiagram
    participant S as Service (e.g. Docs)
    participant M as Menshen
    participant F as Find
    participant O as OpenSearch
    S->>M: exchange the user token<br>(audience find, action:search-find-docs)
    M-->>S: token with scope find:docs:search
    S->>F: POST /api/v1.0/documents/search/ (exchanged token)
    F->>M: introspect the token (cached)
    M-->>F: sub, scopes, client id
    F->>F: select the indices from the find scopes
    F->>O: query the indices with the access filter
    F-->>S: matching documents
```

- **Scopes select the indices.** A search covers every service granted by a
  `find:<service>:search` scope, or only the requested `services`, which must
  all be granted (400 otherwise). A delete runs on the requested `service`,
  which a `find:<service>:delete` scope must grant. A token with no applicable
  scope gets a 403. Which service may search which is configured in Menshen's
  action scopes, not in Find.
- **The access filter selects the documents** inside these indices, in the
  OpenSearch query itself. A user sees the active documents that list their
  `sub` in `users`, or that are not restricted and whose id the service sends
  in `visited`. Group access is not implemented yet. A user may only delete
  documents that list their `sub` in `users`.
- **Introspection results are cached** in Redis for
  `MENSHEN_INTROSPECTION_CACHE_TTL` seconds: an accepted token never beyond
  its expiration, a rejected token for the whole duration, as it cannot become
  valid again. A token Menshen rejects gets a 401; Menshen being unavailable, a
  503, which is not cached.

See [setup-indexer.md](setup-indexer.md) for the configuration of Find, and
[setup-menshen.md](setup-menshen.md) for a local Menshen.
