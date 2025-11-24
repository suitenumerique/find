"""Albert AI related tools"""

import logging
from io import BytesIO, StringIO

from django.conf import settings

import requests

logger = logging.getLogger(__name__)


class AlbertAIError(Exception):
    """Albert AI errors"""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class AlbertAI:
    """
    Client for Albert AI API
    https://albert.api.etalab.gouv.fr/swagger#/
    """

    def __init__(self):
        self.api_key = settings.EMBEDDING_API_KEY
        self.timeout = settings.EMBEDDING_REQUEST_TIMEOUT
        self.doc_parse_url = settings.ALBERT_PARSE_ENDPOINT
        self.embedding_url = settings.EMBEDDING_API_PATH

    def _request_api(self, url, **kwargs):
        """Make authenticated api call"""
        try:
            response = requests.post(
                url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
                **kwargs,
            )
            response.raise_for_status()
            return response
        except requests.HTTPError as e:
            raise AlbertAIError(e.response.json().get("detail", str(e))) from e

    def embedding(self, text, dimensions=None, model=None):
        """
        Get embedding vector for the given text from Albert OpenAI-compatible embedding API
        """
        dimensions = dimensions or settings.EMBEDDING_DIMENSION
        model = model or settings.EMBEDDING_API_MODEL_NAME

        response = self._request_api(
            self.embedding_url,
            json={
                "input": text,
                "model": model,
                "dimensions": dimensions,
                "encoding_format": "float",
            },
        )

        try:
            return response.json()["data"][0]["embedding"]
        except Exception as e:
            raise AlbertAIError(f"Unexpected content : {response.text}") from e

    # pylint: disable=too-many-arguments, too-many-positional-arguments
    def convert(
        self,
        content,
        mimetype="application/pdf",
        pages=None,
        output="markdown",
        encoding="utf-8",
    ):  # noqa : PLR0913
        """
        Convert the content (only pdf) to markdown, json or html using the Albert API
        """
        if isinstance(content, str):
            content = StringIO(content.encode(encoding))
        elif isinstance(content, bytes):
            content = BytesIO(content)

        response = self._request_api(
            self.doc_parse_url,
            files={
                "file": ("input", content, mimetype),
            },
            data={
                "output_format": output,
                "page_range": f"0-{pages}" if pages else None,
            },
        )

        try:
            data = response.json()["data"]
            return "\n".join([page["content"] for page in data])
        except Exception as e:
            raise AlbertAIError(f"Unexpected content : {response.text}") from e
