"""document data for full text evaluation"""

from ..corpus.simple_corpus import documents as simple_corpus_documents

documents = [
    *simple_corpus_documents,
    {"id": "ft-1", "title": "L'éléphant", "content": "L'éléphant s'est échappé"},
    {"id": "ft-2", "title": "Foot", "content": "Le foot est un sport populaire"},
    {"id": "ft-3", "title": "Il va courir", "content": "Il va courir"},
]
