"""Indexation tasks tools"""

import logging
from contextlib import contextmanager
from dataclasses import asdict as dataasdict
from io import BytesIO

from django.conf import settings

import requests

from core import enums
from core.models import IndexDocument, Service

from . import converters
from .albert import AlbertAI, AlbertAIError
from .opensearch import (
    check_hybrid_search_enabled,
    ensure_index_exists,
    format_document,
    opensearch_client,
)

logger = logging.getLogger(__name__)

INDEXABLE_MIMETYPES = ["text/"]


class IndexerError(Exception):
    """Base exception for indexer service"""

    def __init__(self, message, _id=None):
        super().__init__(message)
        self.id = _id

        if isinstance(message, dict):
            self.error_dict = message
        elif isinstance(message, list):
            self.error_list = message
        else:
            self.message = message


class IndexContentError(IndexerError):
    """Raised on content loading or conversion issues"""


class IndexBulkError(IndexerError):
    """Raised on IndexBulkTransaction commit issues"""

    def __init__(self, message, action=None, _id=None, params=None):
        super().__init__(message, _id=_id)
        self.action = action
        self.params = params


class IndexBulkTransaction:
    """
    Helper for bulk changes in opensearch.
    """

    def __init__(
        self,
        index_name,
        client=None,
    ):
        self.client = client or opensearch_client()
        self.index_name = index_name
        self._actions = []
        self._errors = {}

    def errors(self):
        """Returns errors from last commit"""
        return self._errors

    def create(self, uid, data, **kwargs):
        """Create an opensearch entry. Raises if exists"""
        self._actions.append({"create": {"_id": uid, **kwargs}})
        self._actions.append(data)
        return self

    def index_document(self, doc: IndexDocument, **kwargs):
        """Index a document model instance"""
        data = dataasdict(doc)
        _id = data.pop("id")
        return self.index(_id, data=data, **kwargs)

    def index(self, uid, data, **kwargs):
        """Index an openseach entry (create or replace)"""
        self._actions.append({"index": {"_id": uid, **kwargs}})
        self._actions.append(data)
        return self

    def update(self, uid, data, **kwargs):
        """Update an openseach entry"""
        self._actions.append({"update": {"_id": uid, **kwargs}})
        self._actions.append({"doc": data})
        return self

    def commit(self, raise_on_status=False, refresh=False):
        """Send all actions to opensearch database & create the index if needed."""
        # No action, do nothing
        if not self._actions:
            return

        # Build index if needed.
        ensure_index_exists(self.index_name)

        response = self.client.bulk(
            index=self.index_name, body=self._actions, refresh=refresh
        )

        errors = self._errors = []
        self._actions = []

        for item in response["items"]:
            for action, result in item.items():
                status_code = result["status"]

                if status_code >= 300:
                    message = result.get("error", {}).get("reason", "Unknown error")

                    errors.append(
                        IndexBulkError(
                            message, action=action, _id=result.get("_id"), params=result
                        )
                    )

        if errors and raise_on_status:
            raise IndexBulkError(errors)


@contextmanager
def openbulk(index_name, client=None, raise_on_status=False, refresh=False):
    """
    Create a bulk transaction and commit it swiftly after use.
    """
    transaction = IndexBulkTransaction(index_name, client=client)
    yield transaction
    transaction.commit(raise_on_status=raise_on_status, refresh=refresh)


def offsetpaginate(*index_names, query, sort=None, size=100, client=None):
    """
    Paginator based on the next offset filter. Iterates on batches of 'limit' size.
    """
    client = client or opensearch_client()
    sort = sort or [{"_id": "asc"}]
    index = ",".join(index_names)

    body = {
        "query": query or {},
        "sort": sort,
        "size": size,
    }
    page = client.search(
        body=body,
        index=index,
        seq_no_primary_term=True,
        ignore_unavailable=True,
    )

    hits = page["hits"]["hits"]
    count = len(hits)

    if count > 0:
        yield hits

    while count == size:
        page = client.search(
            index=index,
            body={
                **body,
                "search_after": hits[-1]["sort"],
            },
            seq_no_primary_term=True,
            ignore_unavailable=True,
        )
        hits = page["hits"]["hits"]
        count = len(hits)

        if count > 0:
            yield hits


def hit_to_doc(hit):
    """Returns an IndexDocument instance from opensearch hit data"""
    doc = IndexDocument.from_dict({**hit["_source"], "id": hit["_id"]})
    doc.hit = hit
    return doc


def match_mimetype_glob(mimetype, pattern):
    """
    Returns true if the mimetype match with the pattern.
    If a pattern ends with / all subtypes are valid, if not it have to
    perfectly match. e.g :
      - application/pdf only match "application/pdf" and not "application/pdf+bin"
      - application/ match any "application/*"
    """
    if len(mimetype) < 1:
        return False

    if pattern.endswith("/"):
        return mimetype.startswith(pattern)

    return mimetype == pattern


def is_allowed_mimetype(mimetype, patterns):
    """
    Returns true if the mimetype is not empty and matches any of the allowed patterns.
    """
    return len(mimetype) > 0 and any(
        match_mimetype_glob(mimetype, pattern) for pattern in patterns
    )


class IndexerTaskService:
    """
    Service used by indexation tasks for content loading, format conversion
    and embedding
    """

    # V2 : Use settings to define the list of converters
    converters = {"application/pdf": converters.pdf_to_markdown}

    def __init__(
        self, service: Service, batch_size=100, client=None, force_refresh=None
    ):
        self.service = service
        self.batch_size = batch_size
        self.client = client or opensearch_client()
        self.force_refresh = force_refresh or settings.INDEXER_FORCE_REFRESH
        self.download_timeout = settings.INDEXER_DOWNLOAD_TIMEOUT

    def get_converter(self, mimetype):
        """
        Retrieve a converter for the mimetype or None if the mimitype is allowed
        for indexation.
        """
        try:
            if is_allowed_mimetype(mimetype, INDEXABLE_MIMETYPES):
                return None

            return self.converters[mimetype]
        except KeyError as e:
            raise IndexContentError(
                f"No such converter for the unindexable mimetype {mimetype}"
            ) from e

    def process_content(self, document, content):
        """Transforms the document file data into an indexable format"""
        try:
            converter = self.get_converter(document.mimetype)

            if converter is not None:
                # A converter only accepts a BytesIO
                stream = (
                    BytesIO(content.encode()) if isinstance(content, str) else content
                )
                output = converter(stream)
            else:
                # no need to convert
                output = content if isinstance(content, str) else content.read()

            return output.decode() if isinstance(output, bytes) else output
        except IndexContentError as e:
            e.id = document.id
            raise e
        except Exception as e:
            raise IndexContentError(
                f"Unable to convert content with the mimetype {document.mimetype}",
                _id=document.id,
            ) from e

    def stream_content(self, document):
        """Open download stream containing the file data"""
        try:
            response = requests.get(
                document.content_uri, stream=True, timeout=self.download_timeout
            )
            response.raise_for_status()
            return response.raw
        except requests.RequestException as e:
            raise IndexerError(str(e), _id=document.id) from e

    def search(self, query, *, sort=None, as_batch=False, batch_size=None):
        """Returns the paginated results from the opensearch query as an iterable"""
        pages = offsetpaginate(
            self.service.index_name,
            query=query,
            sort=sort,
            size=batch_size or self.batch_size,
            client=self.client,
        )

        if as_batch:
            yield from pages
        else:
            for hits in pages:
                yield from hits

    def search_documents(self, query, *, sort=None, as_batch=False, batch_size=None):
        """
        Returns the paginated results from the opensearch query as IndexDocument instances
        """
        if as_batch:
            for hits in self.search(
                query, sort=sort, as_batch=True, batch_size=batch_size
            ):
                yield [hit_to_doc(hit) for hit in hits]
        else:
            for hit in self.search(query, sort=sort, batch_size=batch_size):
                yield hit_to_doc(hit)

    def process_all(self, batch_size=None):
        """
        Gets all the documents in waiting status to load and convert their content
        Returns an error dict.
        """
        errors = []
        index_name = self.service.index_name
        batch_size = batch_size or self.batch_size
        doc_batches = self.search_documents(
            query={
                "bool": {
                    "must": [
                        {
                            "term": {
                                "content_status": enums.ContentStatusEnum.LOADED.value
                            }
                        },
                        {"term": {"is_active": True}},
                    ]
                }
            },
            batch_size=batch_size,
            as_batch=True,
        )

        for docs in doc_batches:
            with openbulk(
                index_name, client=self.client, refresh=self.force_refresh
            ) as actions:
                for doc in docs:
                    try:
                        # V2 : Use asyncio loop to parallelize conversion
                        content = self.process_content(doc, doc.content)

                        actions.update(
                            doc.id,
                            data={
                                "content_status": enums.ContentStatusEnum.READY.value,
                                "content": content,
                            },
                            # if_seq_no and if_primary_term ensure we only update indexes
                            # if the document hasn't changed
                            if_seq_no=doc.hit["_seq_no"],
                            if_primary_term=doc.hit["_primary_term"],
                        )
                    except IndexerError as e:
                        errors.append(e)

            errors.extend(actions.errors())

        return errors

    def load_n_process_all(self, batch_size=None):
        """
        Gets all the documents in waiting status to load and convert their content
        Returns an error dict.
        """
        errors = []
        index_name = self.service.index_name
        batch_size = batch_size or self.batch_size
        doc_batches = self.search_documents(
            query={
                "bool": {
                    "must": [
                        {
                            "term": {
                                "content_status": enums.ContentStatusEnum.WAIT.value
                            }
                        },
                        {"term": {"is_active": True}},
                    ]
                }
            },
            batch_size=batch_size,
            as_batch=True,
        )

        for docs in doc_batches:
            with openbulk(
                index_name, client=self.client, refresh=self.force_refresh
            ) as actions:
                for doc in docs:
                    try:
                        # V2 : Use asyncio loop to parallelize downloads
                        content = self.process_content(doc, self.stream_content(doc))

                        actions.update(
                            doc.id,
                            data={
                                "content_status": enums.ContentStatusEnum.READY.value,
                                "content": content,
                            },
                            # if_seq_no and if_primary_term ensure we only update indexes
                            # if the document hasn't changed
                            if_seq_no=doc.hit["_seq_no"],
                            if_primary_term=doc.hit["_primary_term"],
                        )
                    except IndexerError as e:
                        errors.append(e)

            errors.extend(actions.errors())

        return errors

    def embed_all(self, model_name=None, batch_size=None):
        """
        Re-index all the document in "ready" status without embbeding or with a different model.
        """
        errors = []

        # Hybrid search is disabled, skip it
        if not check_hybrid_search_enabled():
            return ()

        index_name = self.service.index_name
        batch_size = batch_size or self.batch_size
        model_name = model_name or settings.EMBEDDING_API_MODEL_NAME
        albert = AlbertAI()
        doc_batches = self.search_documents(
            query={
                "bool": {
                    "must": [
                        {
                            "term": {
                                "content_status": enums.ContentStatusEnum.READY.value
                            }
                        },
                        {"term": {"is_active": True}},
                    ],
                    "should": [
                        {"bool": {"must_not": {"exists": {"field": "embedding"}}}},
                        {
                            "bool": {
                                "must_not": {"term": {"embedding_model": model_name}}
                            }
                        },
                    ],
                    "minimum_should_match": 1,
                },
            },
            batch_size=batch_size,
            as_batch=True,
        )

        for docs in doc_batches:
            with openbulk(
                index_name, client=self.client, refresh=self.force_refresh
            ) as actions:
                for doc in docs:
                    try:
                        # V2 : Use asyncio loop to parallelize embedding
                        embedding = albert.embedding(
                            text=format_document(doc.title, doc.content),
                            model=model_name,
                        )
                    except AlbertAIError as e:
                        errors.append(
                            IndexerError(
                                f"Unable to build embedding for the document : {e.message}",
                                _id=doc.id,
                            )
                        )
                    else:
                        actions.update(
                            doc.id,
                            data={
                                "embedding": embedding,
                                "embedding_model": model_name,
                            },
                            # if_seq_no and if_primary_term ensure we only update indexes
                            # if the document hasn't changed
                            if_seq_no=doc.hit["_seq_no"],
                            if_primary_term=doc.hit["_primary_term"],
                        )

            errors.extend(actions.errors())

        return errors

    def index(self, documents):
        """
        Index all the documents and initialize the status depending of the availability
        of their content.
        Returns the errors from the commit and convertion
        """
        errors = []

        with openbulk(
            self.service.index_name, client=self.client, refresh=self.force_refresh
        ) as actions:
            for doc in documents:
                if doc.content_uri and not doc.content:
                    # Without content and a dowload uri : set WAIT status
                    doc.content_status = enums.ContentStatusEnum.WAIT
                elif not is_allowed_mimetype(doc.mimetype, INDEXABLE_MIMETYPES):
                    # A content but not directly indexable (e.g xml or html content) : process them
                    try:
                        doc.content = self.process_content(doc, doc.content)
                        doc.content_status = enums.ContentStatusEnum.READY
                    except IndexContentError as err:
                        # If process has failed, set LOADED status for a retry.
                        # V2 : Add retry mechanism ?
                        doc.content_status = enums.ContentStatusEnum.LOADED
                        errors.append(IndexBulkError(str(err), _id=doc.id))
                else:
                    # The content exists and is indexable : set READY
                    doc.content_status = enums.ContentStatusEnum.READY

                actions.index_document(doc)

        errors.extend(actions.errors())
        return errors
