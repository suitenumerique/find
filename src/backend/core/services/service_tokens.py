"""Authentication of the services indexing documents with their service token."""

from ..models import Service, hash_token


async def get_service_by_token(token):
    """
    Get the active service owning a token.

    Only the token hash is stored, so the token is looked up by its hash. The
    whole service is loaded: accessing a deferred field from async code would
    run a synchronous query.

    Returns:
        The active Service of the token, or None if no active service owns it.
    """
    if not token:
        return None
    try:
        return await Service.objects.aget(token_hash=hash_token(token), is_active=True)
    except Service.DoesNotExist:
        return None
