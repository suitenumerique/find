## Decision TLDR;

We will replace Django REST Framework with **django-ninja**, serve Find over
**ASGI with async views**, talk to OpenSearch through **`AsyncOpenSearch`**, and
authenticate user requests with tokens exchanged by **Menshen** instead of the
`django-lasuite` OIDC resource server. The calling service, and the services it
may search, are identified by **OAuth scopes** granted by Menshen. We stay on
Django.

## Status

Accepted (2026-10-27). Implementation plan amended (2026-10-27): no spike,
and a single switch from DRF to django-ninja.

## Context

Find is not in production yet and is entering a new development phase, so
breaking changes to the API and its integration with Docs and Drive are still
cheap.

### What the API does

Find exposes three endpoints (`documents/index/`, `documents/search/`,
`documents/delete/`). No Django model is exposed through the API: documents
live in OpenSearch, and the only model, `Service`, is managed through the Django
admin.

Each request is dominated by network I/O:

- search / delete: token introspection (HTTP) → `Service` lookup (PostgreSQL)
  → OpenSearch query;
- index: `Service` lookup → `indices.get` → OpenSearch bulk write.

The only CPU-bound work is Pydantic validation and `py3langid` language
detection during indexing.

### How DRF and Pydantic are used today

DRF is only used as plumbing: `APIView`, authentication and permission classes,
the JSON parser, `Response`, a custom exception handler, and drf-spectacular for
OpenAPI. No serializer, viewset, router or pagination is used. Validation is
done with Pydantic (`core/schemas.py`), and `core/api.py` converts Pydantic
errors into 400 responses.

This mix has visible costs:

- **The OpenAPI schema is empty.** drf-spectacular infers bodies from
  serializers, and no view uses `@extend_schema`, so request and response
  bodies are not documented. Yet this schema is the contract with Docs and
  Drive.
- **Three error formats**: Pydantic errors (`[{msg, type, loc}]`), DRF errors
  (`{"detail": ...}`), and the per-document results of bulk indexing.
- **Responses are not modelled**: search returns raw OpenSearch hits (#179).
- **Everything is synchronous**: a gunicorn worker is blocked for each network
  round trip, and a slow identity provider exhausts the worker pool.

### Authentication is changing anyway

User requests are currently authenticated with
`lasuite.oidc_resource_server`, which is DRF-only and synchronous (blocking
`requests` calls). La Suite is replacing this mechanism with
[Menshen](https://github.com/suitenumerique/menshen), an OAuth 2.0 Token
Exchange server (RFC 8693): a source service (Docs, Drive) exchanges the user's
access token for a token targeting Find, and Find introspects it with Menshen
(RFC 7662).

The current resource-server integration will be removed. So the main cost of
leaving DRF (porting the authentication layer) has to be paid regardless.

Menshen itself is built on `django==6.1`, `django-ninja==1.7.1`, `uvicorn` and
Pydantic schemas, and uses ninja's `AuthRateThrottle` and exception handlers.
That gives La Suite a precedent for the stack proposed here.

## Considered alternatives

### Keep DRF + Pydantic, fix the integration

Add `@extend_schema` (drf-spectacular ships a Pydantic extension), unify error
handling, and add response models.

| Pros | Cons |
| --- | --- |
| No migration | Stays synchronous: DRF's core (auth, permissions, throttling) is sync |
| Same stack as Docs and Drive | Still two validation/schema systems glued together |
| Small effort | The authentication layer must be rewritten for Menshen anyway |

### DRF + adrf (async DRF views)

| Pros | Cons |
| --- | --- |
| Keeps DRF idioms | Async is a third-party add-on, not part of DRF's design |
| Async views possible | Authentication, permissions and throttling stay mostly sync |
| | Does not solve the Pydantic / OpenAPI mismatch |

### DRF serializers everywhere

| Pros | Cons |
| --- | --- |
| One consistent system, native OpenAPI | Slower validation on bulk indexing |
| Same stack as Docs and Drive | More verbose for non-model data |
| | Still synchronous |

### Plain Django async views + Pydantic

| Pros | Cons |
| --- | --- |
| Minimal dependencies, fully async | OpenAPI generation, auth, throttling and error handling must be rebuilt |
| | More code to own for no functional gain |

### FastAPI (leave Django)

| Pros | Cons |
| --- | --- |
| Native async, Pydantic and OpenAPI | Loses the Django admin (service registration, self-test page) |
| | Loses migrations, django-configurations, `django-lasuite` |
| | Leaves the La Suite ecosystem; amounts to a rewrite |

### django-ninja (async)

| Pros | Cons |
| --- | --- |
| Native async views and async auth | One more framework in the La Suite back ends (mitigated: Menshen uses it) |
| Pydantic-native: current schemas reused almost as-is | Team must learn ninja (small API surface) |
| OpenAPI generated from request and response schemas | `menshen_client` is sync and needs an async counterpart |
| Single exception-handling mechanism | |
| Built-in throttling | |
| Stays on Django: ORM, admin, settings, conventions | |

### Comparison

| Criteria | DRF + Pydantic | DRF + adrf | Plain async views | FastAPI | **django-ninja** |
| --- | --- | --- | --- | --- | --- |
| Async end-to-end | ❌ | ⚠️ | ✅ | ✅ | ✅ |
| Pydantic-native | ⚠️ | ⚠️ | ✅ | ✅ | ✅ |
| OpenAPI from schemas | ⚠️ | ⚠️ | ❌ | ✅ | ✅ |
| Django admin and ORM | ✅ | ✅ | ✅ | ❌ | ✅ |
| Used in La Suite | Docs, Drive | — | — | — | Menshen |
| Migration effort | Low | Medium | Medium | High | Medium |

## Decision

We adopt **django-ninja with async views, served over ASGI**, and integrate
**Menshen** for user authentication.

### Target stack

- **API**: django-ninja; `async def` endpoints; Pydantic request **and
  response** schemas; a single exception handler producing one error format.
- **Server**: ASGI with uvicorn (as Menshen does), or gunicorn with uvicorn
  workers; replaces the WSGI gunicorn setup in the Dockerfile and Helm chart.
- **OpenSearch**: `opensearchpy.AsyncOpenSearch` (the `async` extra), one
  client per process.
- **ORM**: Django's async API (`aget`, `async for`) for `Service` lookups.
- **CPU-bound work**: bulk validation and language detection run in
  `asyncio.to_thread` so they don't block the event loop.
- **Middleware**: keep only what the API needs. Sessions, messages and CSRF only
  matter for the admin, and CORS is not needed for a server-to-server API
  (#177). Remaining middleware must be async-capable to avoid sync/async
  switching on every request.
- **Admin**: unchanged, served synchronously under ASGI.

### Authentication

- **User requests (search, delete)**: Menshen-exchanged bearer tokens,
  validated by an async ninja auth class that introspects them with Menshen and
  caches the result for a short TTL (see "Open questions").
- **Indexing**: keeps per-service tokens (Menshen covers tokens issued on behalf
  of a user, and indexing happens without one). Tokens are stored hashed rather
  than in plaintext.
- **Async Menshen client**: `menshen_client` uses blocking `requests`. We will
  contribute an async `introspect` (based on `httpx.AsyncClient`) to
  `menshen_client` rather than maintain a private copy. Until then, the sync
  client is called through `asyncio.to_thread`.

### Service identification by scopes

Find selects the indices a request may touch from the caller's identity. Today
the token audience is matched to `Service.client_id`. This no longer works with
Menshen: in its introspection response, `aud` is the target (Find itself),
`client_id` is Menshen's own client id, and no `act` or `azp` claim names the
source service. Find therefore cannot tell Docs from Drive from the token alone.

We encode **what the caller may do, and on which service's documents, in OAuth
scopes** granted by Menshen's token exchange rules (`TokenExchangeRule` /
`ScopeGrant`). Scopes follow Menshen's `service:resource:action` convention,
with the indexed service name as the resource:

- `find:<service>:search`: search the documents indexed by `<service>`
  (e.g. `find:docs:search`, `find:drive:search`);
- `find:<service>:delete`: delete documents indexed by `<service>`.

Find's rules:

- **Search**: the searchable indices are the services named in the granted
  `find:*:search` scopes. If the request's `services` parameter is set, it must
  be a subset of them (otherwise 400) and the search is restricted to it. If it
  is empty, all granted services are searched. This replaces the current
  behaviour, where `services` is validated but ignored (#172).
- **Delete**: the request's `service` must be covered by a
  `find:<service>:delete` scope, and the delete runs on that service's index
  only (#173).
- A token with no applicable `find:` scope gets a 403. Scopes naming an unknown
  or inactive `Service` are ignored.
- The per-document access filter (`users`, `groups`, `reach`, `visited`) is
  unchanged: scopes decide **which indices** a caller may query, never which
  documents a user may see inside them.

As a result, the "Allowed services for search" configuration moves from Find's
admin to Menshen. Authorization between services is configured in one place,
and Find only reads scopes. Emitting the RFC 8693 `act` claim (or `azp`) with
the source service would still be useful for logging and auditing, but Find
does not depend on it.

### Removed

`djangorestframework`, `drf-spectacular`, `drf-spectacular-sidecar`,
`lasuite.oidc_resource_server` usage, `core.authentication.ResourceUser` /
`FinderResourceServerBackend`, and the `Service.client_id` and
`Service.services` fields (replaced by scopes). Celery and Redis are decided
separately (#183); if they are removed, a shared cache for introspection still
needs a backend.

## Open questions (to settle with the Menshen team before implementation)

1. **Introspection on every request.** At the time of writing, Menshen exposes
   exchange, introspect and revoke endpoints but no JWKS endpoint, so Find cannot
   validate JWT tokens locally. We will cache introspection results keyed by a
   token hash. Because tokens can be revoked, the TTL must stay short (seconds
   to a minute) and never exceed `exp`. Will Menshen publish JWKS for its JWT
   tokens? Menshen PR #71 (open) stores the signing keys as a standard JWK
   set, a prerequisite for a JWKS endpoint, but does not expose one. Local
   validation would also accept revoked tokens until `exp` (5 minutes by
   default), so introspection stays the default until this is settled.
2. **Subject identity.** *Resolved (2026-10-27).* Docs and Drive index the
   users' OIDC `sub` in `users`, the identity provider issues the same `sub`
   to every service, and Menshen copies the subject token's `sub` into the
   exchanged token and returns it on introspection. The `users` access filter
   keeps working unchanged; the first end-to-end exchange (step 2) confirms it.
3. **Caller-side cost.** Docs and Drive must exchange the user token before
   calling Find, and should cache the exchanged token until it expires, or every
   search (including search-as-you-type) pays an extra round trip to Menshen.
   Tracked in suitenumerique/docs#2920 and suitenumerique/drive#934: migrate
   the Find search call to Menshen, then cache the exchanged token.

## Consequences

### Positive

- End-to-end async I/O: fewer processes for the same load, and requests no
  longer block a worker while waiting on the identity provider or OpenSearch.
- A generated, accurate OpenAPI schema for Docs and Drive.
- One validation and schema system (Pydantic) and one error format.
- The authentication rewrite required by Menshen is done once, on the target
  stack.
- Authorization rules (who may search which service) are centralized in
  Menshen, and cross-service scoping (#172, #173) gets a single, explicit rule.
- Same stack as Menshen, so patterns and people can move between the two
  projects.

### Negative

- Find diverges from Docs and Drive, which stay on DRF.
- The three endpoints, their tests and the deployment (Dockerfile, Helm) must
  be migrated.
- Find depends on Menshen being available for every user request (mitigated by
  the introspection cache).
- Async code needs care: blocking calls, CPU-bound work and sync middleware can
  silently erase the gains.
- Which service may search which is no longer visible in Find's admin; it has
  to be read from Menshen's rules.

### Risks

- Menshen's rules become security-sensitive for Find: a rule granting too broad
  `find:*` scopes opens other services' indices to a caller (the per-document
  access filter still applies). Find's scopes must be reviewed like any other
  access-control change.
- The async gain may be smaller than expected if most latency is OpenSearch
  query time rather than waiting. Find is not deployed yet, so this can only be
  measured once it runs on ASGI with real traffic.
- The `menshen_client` async contribution could be delayed; the
  `asyncio.to_thread` fallback limits this risk.

## Implementation plan

1. **Restore endpoint tests (#171)** with framework-independent HTTP tests;
   they are the safety net for the migration.
2. **Configure Menshen** with the `find:<service>:search` and
   `find:<service>:delete` scopes and the exchange rules for Docs and Drive, and
   settle the remaining open questions with the Menshen team.
3. **Prepare the migration on DRF**, in small independent changes that do not
   depend on the web framework: response schemas (#179), scope-based service
   selection, an async Menshen introspection service with its cache,
   `AsyncOpenSearch` and async versions of the search, delete and indexing
   service functions, hashed service tokens, and the fixes for #172–#175
   that do not depend on authentication. Each piece is tested on its own.
4. **Switch from DRF to django-ninja in a single change**: the three endpoints
   move to async ninja at the same URLs, user authentication moves to Menshen
   and service selection to scopes, and DRF, drf-spectacular and the
   resource-server code are removed. DRF and ninja never serve the API side by
   side. The endpoint tests stay unchanged except for the authentication helper
   and the bugs it fixes.
5. **Clean up and switch deployment to ASGI**: remove `Service.client_id` and
   `Service.services`, keep only async-capable middleware (#177), switch the
   Dockerfile, gunicorn config and Helm chart to ASGI, and update
   `docs/architecture.md` (#186).

Step 3 used to be a spike load-testing an async search endpoint against the
current implementation. It was dropped: Find is not deployed anywhere, so
there is no baseline worth comparing against, and keeping both frameworks
side by side for the comparison would cost more than it teaches.

## References

- Menshen: <https://github.com/suitenumerique/menshen>
- RFC 8693, OAuth 2.0 Token Exchange: <https://www.rfc-editor.org/rfc/rfc8693>
- RFC 7662, OAuth 2.0 Token Introspection: <https://www.rfc-editor.org/rfc/rfc7662>
- django-ninja: <https://django-ninja.dev/>
- Related issues: #171, #172, #173, #177, #179, #181, #183, #184, #186
