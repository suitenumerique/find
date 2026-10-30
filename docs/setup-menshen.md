# Run Find with a local Menshen

Find is moving its user authentication to [Menshen](https://github.com/suitenumerique/menshen),
La Suite's OAuth 2.0 Token Exchange server (see
[ADR-0001](adr/ADR-0001-20261019-async-django-ninja-and-menshen.md)): Docs and
Drive exchange the user's access token for a token targeting Find, and Find
introspects it with Menshen. This guide sets up a local Menshen configured for
Find, for development only.

## Start Menshen

In a Menshen checkout (anywhere on your machine):

```bash
git clone https://github.com/suitenumerique/menshen.git
cd menshen
make bootstrap  # first time; `make run` afterwards
```

Menshen runs on http://localhost:8071 (admin at `/admin`, `admin`/`admin`) with
its own Keycloak on http://localhost:8080 (realm `menshen`, user
`menshen`/`menshen`). Both stacks share the `lasuite-network` Docker network,
where Menshen is reachable as `http://menshen:8000`.

## Find's configuration in Menshen

There is nothing to configure: Menshen's development Keycloak realm and demo
fixtures (created by `make bootstrap`, or `make demo` to reset them) already
contain Find, Docs and Drive. Keycloak only imports its realm when it does not
exist yet: if your Menshen stack predates this configuration, recreate it with
`docker compose down -v && make bootstrap` in your Menshen checkout.

To check it, from Find's repository:

```bash
make menshen-check  # exchange a token end to end
```

Keycloak's `menshen` realm has `docs` and `drive` OIDC clients (secrets
`docs-oidc-secret` and `drive-oidc-secret`), and Menshen has:

| Service provider | Audience id | Menshen credentials |
| --- | --- | --- |
| Find (target) | `find` | `find` / `find-secret` |
| Docs (source) | `docs` | `docs` / `docs-secret` |
| Drive (source) | `drive` | `drive` / `drive-secret` |

and the Docs → Find and Drive → Find exchange rules. Docs and Drive do not
request Find's scopes directly but an **action scope**, which Menshen replaces
in the exchanged token by the scope it grants:

| Rule | Action scope | Granted scope |
| --- | --- | --- |
| Docs → Find | `action:search-find-docs` | `find:docs:search` |
| Docs → Find | `action:delete-find-docs` | `find:docs:delete` |
| Drive → Find | `action:search-find-drive` | `find:drive:search` |
| Drive → Find | `action:delete-find-drive` | `find:drive:delete` |

An action scope must be requested alone, one per exchange. Find never sees it:
it only reads the granted `find:` scopes when introspecting the token.

In `find:<service>:<action>`, `<service>` is the service **whose documents**
the caller may act on, not the caller. Docs and Drive only search and delete
their own documents. Cross-service search is still supported for services
added later: an action can grant several `find:<service>:search` scopes, which
lets its source search those services' documents (e.g. granting
`find:drive:search` for `action:search-find-docs` would let Docs search
Drive's documents). This replaces the "Allowed services for search" setting of
Find's admin. Scopes only select which indices are searched; Find's
per-document access filter (`users`, `reach`, `visited`) still applies inside
them.

The `docs` and `drive` Keycloak clients add `menshen` to their access tokens'
audience (`oidc-audience-mapper`): Keycloak refuses to introspect a token for a
client that is not in its audience, and Menshen introspects the user token
before exchanging it. Real identity providers must allow the same.

In Menshen's development realm, the `sub` claim is mapped to the user's email
(`menshen@menshen.world`); real identity providers use an opaque identifier.

`menshen-check` gets a token for the `menshen` user from Keycloak as Docs,
exchanges it with Menshen for audience `find` with the
`action:search-find-docs` action scope, introspects it as Find, and checks that
the token is active for audience `find`, that the user's `sub` is preserved and
that `find:docs:search` is granted. It then checks that the other actions of
Docs and Drive grant their scope to the same user, a delete action no other
scope and a search action no delete scope, and that ungranted exchanges are
refused.

## Exchange a token by hand

```bash
# User token, as Docs
USER_TOKEN=$(curl -s http://localhost:8080/realms/menshen/protocol/openid-connect/token \
  -d grant_type=password -d client_id=docs -d client_secret=docs-oidc-secret \
  -d username=menshen -d password=menshen -d scope=openid | jq -r .access_token)

# Exchange, as Docs
FIND_TOKEN=$(curl -s -u docs:docs-secret http://localhost:8071/auth/token/exchange/ \
  -d grant_type=urn:ietf:params:oauth:grant-type:token-exchange \
  -d subject_token="$USER_TOKEN" \
  -d subject_token_type=urn:ietf:params:oauth:token-type:access_token \
  -d audience=find -d scope="action:search-find-docs" | jq -r .access_token)

# Introspect, as Find
curl -s -u find:find-secret http://localhost:8071/auth/token/introspect/ \
  -d token="$FIND_TOKEN" | jq
```
