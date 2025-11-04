"""Tests Service model for find's core app."""

import base64
import json
import logging
from functools import partial
from typing import List

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from joserfc import jwe as jose_jwe
from joserfc import jwt as jose_jwt
from joserfc.jwk import RSAKey
from jwt.utils import to_base64url_uint
from opensearchpy.exceptions import NotFoundError
from opensearchpy.helpers import bulk

from core import factories
from core.services import opensearch

logger = logging.getLogger(__name__)


def enable_hybrid_search(settings):
    """Enable hybrid search settings for tests."""
    settings.HYBRID_SEARCH_ENABLED = True
    settings.HYBRID_SEARCH_WEIGHTS = [0.3, 0.7]
    settings.EMBEDDING_API_KEY = "test-api-key"
    settings.EMBEDDING_API_PATH = "https://test.embedding.api/v1/embeddings"
    settings.EMBEDDING_API_MODEL_NAME = "embeddings-small"
    settings.EMBEDDING_DIMENSION = 1024


def bulk_create_documents(document_payloads):
    """Create documents in bulk from payloads"""
    return [
        factories.DocumentSchemaFactory.build(**document_payload, users=["user_sub"])
        for document_payload in document_payloads
    ]


def delete_search_pipeline():
    """Delete the hybrid search pipeline if it exists"""
    try:
        opensearch.opensearch_client().transport.perform_request(
            method="DELETE",
            url=f"/_search/pipeline/{opensearch.HYBRID_SEARCH_PIPELINE_ID}",
        )
    except NotFoundError:
        logger.info("Search pipeline not found, nothing to delete.")


def delete_test_indices():
    """Drop all search index containing the 'test' word"""
    opensearch.opensearch_client().indices.delete(index="*test*")


def prepare_index(index_name, documents: List, cleanup=True):
    """Prepare the search index before testing a query on it."""
    if cleanup:
        delete_test_indices()

    opensearch.ensure_index_exists(index_name)

    # Index new documents
    actions = [
        {
            "_op_type": "index",
            "_index": index_name,
            "_id": doc["id"],
            "_source": {k: v for k, v in doc.items() if k != "id"},
        }
        for doc in documents
    ]
    bulk(opensearch.opensearch_client(), actions)

    # Force refresh again so all changes are visible to search
    opensearch.opensearch_client().indices.refresh(index=index_name)

    count = opensearch.opensearch_client().count(index=index_name)["count"]
    assert count == len(documents), f"Expected {len(documents)}, got {count}"


def build_authorization_bearer(token="some_token"):
    """
    Build an Authorization Bearer header value from a token.

    This can be used like this:
    client.post(
        ...
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer('some_token')}",
    )
    """
    return base64.b64encode(token.encode("utf-8")).decode("utf-8")


def setup_oicd_jwt_resource_server(
    responses,
    settings,
    sub="some_sub",
    audience="some_client_id",
):
    """
    Setup settings for a resource server with JWT backend.
    Simulate an encrypted token introspection.
    NOTE : Use it with @responses.activate or the fake introspection view will not work.
    """
    token_data = {
        "sub": sub,
        "iss": "https://oidc.example.com",
        "aud": audience,
        "client_id": "some_service_provider",
        "scope": "docs",
        "active": True,
    }

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    unencrypted_pem_private_key = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )

    pem_public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    settings.OIDC_RS_PRIVATE_KEY_STR = unencrypted_pem_private_key.decode("utf-8")
    settings.OIDC_RS_ENCRYPTION_KEY_TYPE = "RSA"
    settings.OIDC_RS_ENCRYPTION_ENCODING = "A256GCM"
    settings.OIDC_RS_ENCRYPTION_ALGO = "RSA-OAEP"
    settings.OIDC_RS_SIGNING_ALGO = "RS256"
    settings.OIDC_RS_CLIENT_ID = audience
    settings.OIDC_RS_CLIENT_SECRET = "some_client_secret"
    settings.OIDC_RS_SCOPES = ["openid", "docs", "email"]

    settings.OIDC_OP_URL = "https://oidc.example.com"
    settings.OIDC_OP_JWKS_ENDPOINT = "https://oidc.example.com/jwks"
    settings.OIDC_OP_INTROSPECTION_ENDPOINT = "https://oidc.example.com/introspect"

    settings.OIDC_VERIFY_SSL = False
    settings.OIDC_TIMEOUT = 5
    settings.OIDC_PROXY = None
    settings.OIDC_CREATE_USER = False

    # Mock the JWKS endpoint
    public_numbers = private_key.public_key().public_numbers()
    responses.add(
        responses.GET,
        settings.OIDC_OP_JWKS_ENDPOINT,
        body=json.dumps(
            {
                "keys": [
                    {
                        "kty": settings.OIDC_RS_ENCRYPTION_KEY_TYPE,
                        "alg": settings.OIDC_RS_SIGNING_ALGO,
                        "use": "sig",
                        "kid": "1234567890",
                        "n": to_base64url_uint(public_numbers.n).decode("ascii"),
                        "e": to_base64url_uint(public_numbers.e).decode("ascii"),
                    }
                ]
            }
        ),
    )

    def encrypt_jwt(json_data):
        """Encrypt the JWT token for the backend to decrypt."""
        token = jose_jwt.encode(
            {
                "kid": "1234567890",
                "alg": settings.OIDC_RS_SIGNING_ALGO,
            },
            json_data,
            RSAKey.import_key(unencrypted_pem_private_key),
            algorithms=[settings.OIDC_RS_SIGNING_ALGO],
        )

        return jose_jwe.encrypt_compact(
            protected={
                "alg": settings.OIDC_RS_ENCRYPTION_ALGO,
                "enc": settings.OIDC_RS_ENCRYPTION_ENCODING,
            },
            plaintext=token,
            public_key=RSAKey.import_key(pem_public_key),
            algorithms=[
                settings.OIDC_RS_ENCRYPTION_ALGO,
                settings.OIDC_RS_ENCRYPTION_ENCODING,
            ],
        )

    responses.add(
        responses.POST,
        "https://oidc.example.com/introspect",
        body=encrypt_jwt(
            {
                "iss": "https://oidc.example.com",
                "aud": audience,  # settings.OIDC_RS_CLIENT_ID
                "token_introspection": token_data,
            }
        ),
    )


def setup_oicd_resource_server(
    responses,
    settings,
    sub="some_sub",
    audience="some_client_id",
    introspect=None,
):  # pylint: disable=too-many-arguments
    """
    Setup settings for a resource server.
    Simulate a token introspection.
    NOTE : Use it with @responses.activate or the fake introspection view will not work.
    """
    token_data = {
        "sub": sub,
        "iss": "https://oidc.example.com",
        "aud": audience,
        "client_id": audience,
        "scope": "docs",
        "active": True,
    }

    settings.OIDC_RS_ENCRYPTION_KEY_TYPE = "RSA"
    settings.OIDC_RS_ENCRYPTION_ENCODING = "A256GCM"
    settings.OIDC_RS_ENCRYPTION_ALGO = "RSA-OAEP"
    settings.OIDC_RS_SIGNING_ALGO = "RS256"
    settings.OIDC_RS_CLIENT_ID = audience
    settings.OIDC_RS_CLIENT_SECRET = "some_client_secret"
    settings.OIDC_RS_SCOPES = ["openid", "docs", "email"]

    settings.OIDC_OP_URL = "https://oidc.example.com"
    settings.OIDC_OP_INTROSPECTION_ENDPOINT = "https://oidc.example.com/introspect"

    settings.OIDC_VERIFY_SSL = False
    settings.OIDC_TIMEOUT = 5
    settings.OIDC_PROXY = None
    settings.OIDC_CREATE_USER = False

    if callable(introspect):
        responses.add_callback(
            responses.POST,
            "https://oidc.example.com/introspect",
            callback=partial(introspect, user_info=token_data),
        )
    else:
        responses.add(
            responses.POST,
            "https://oidc.example.com/introspect",
            body=json.dumps(token_data),
        )
