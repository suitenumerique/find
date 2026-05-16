"""Authentication middleware for BoltAPI routes.

Provides route-level middleware for service token and OIDC authentication.
Use with @middleware decorator on specific routes.

Example:
    @api.post("/documents/index")
    @middleware(ServiceAuthMiddleware)
    async def index_document(request: Request, document: Document) -> IndexResponse:
        service_name = request.state.get("service_name")
        ...
"""

from django_bolt.exceptions import HTTPException
from django_bolt.middleware import Middleware
from django_bolt.request import Request

from .bolt_auth import OIDCAuthentication
from .services.registry import get_service_by_token


class ServiceAuthMiddleware(Middleware):
    """Validates service token from Authorization header.

    On success, stores in request.state:
        - service_name: Name of the authenticated service
        - client_id: Client ID of the service

    Usage:
        @api.post("/documents/index")
        @middleware(ServiceAuthMiddleware)
        async def index_document(request: Request, ...) -> ...:
            service_name = request.state.get("service_name")
            client_id = request.state.get("client_id")
    """

    async def process_request(self, request: Request):
        headers = request.headers or {}
        auth_header = headers.get("authorization", "")

        if not auth_header:
            raise HTTPException(
                status_code=401, detail="Service authentication required"
            )

        token = auth_header.split()[-1] if auth_header else None
        if not token:
            raise HTTPException(
                status_code=401, detail="Service authentication required"
            )

        result = get_service_by_token(token)
        if result is None:
            raise HTTPException(
                status_code=401, detail="Service authentication required"
            )

        service_name, service = result

        request.state["service_name"] = service_name
        request.state["client_id"] = service.client_id

        return await self.get_response(request)


class OIDCAuthMiddleware(Middleware):
    """Validates OIDC bearer token from Authorization header.

    On success, stores in request.state:
        - user: ResourceUser object with sub, token_audience, etc.

    Usage:
        @api.post("/documents/search")
        @middleware(OIDCAuthMiddleware)
        async def search_documents(request: Request, ...) -> ...:
            user = request.state.get("user")
            user_sub = user.sub
    """

    def __init__(self, get_response):
        super().__init__(get_response)
        self._oidc_auth = OIDCAuthentication()

    async def process_request(self, request: Request):
        headers = request.headers or {}
        auth_header = headers.get("authorization", "")

        if not auth_header:
            raise HTTPException(status_code=401, detail="Authentication required")

        user = await self._oidc_auth.get_user(None, {"authorization": auth_header})
        if not user or not getattr(user, "sub", None):
            raise HTTPException(status_code=401, detail="Authentication required")

        request.state["user"] = user

        return await self.get_response(request)


class SearchAuthMiddleware(Middleware):
    """Accepts either service token or OIDC bearer token.

    Tries service token first, falls back to OIDC. Populates request.state
    with whichever auth succeeds - handler/builder checks what's present.
    """

    def __init__(self, get_response):
        super().__init__(get_response)
        self._oidc_auth = OIDCAuthentication()

    async def process_request(self, request: Request):
        headers = request.headers or {}
        auth_header = headers.get("authorization", "")

        if not auth_header:
            raise HTTPException(status_code=401, detail="Authentication required")

        token = auth_header.split()[-1] if auth_header else None
        if not token:
            raise HTTPException(status_code=401, detail="Authentication required")

        result = get_service_by_token(token)
        if result is not None:
            service_name, service = result
            request.state["service_name"] = service_name
            request.state["client_id"] = service.client_id
            return await self.get_response(request)

        user = await self._oidc_auth.get_user(None, {"authorization": auth_header})
        if user and getattr(user, "sub", None):
            request.state["user"] = user
            return await self.get_response(request)

        raise HTTPException(status_code=401, detail="Authentication required")
