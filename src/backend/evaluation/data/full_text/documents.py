"""document data for full text evaluation"""

from ..corpus.simple_corpus import documents as simple_corpus_documents

documents = [
    *simple_corpus_documents,
    {
        "id": "456a071a-d433-47f3-a398-b95db6657841",
        "title": "L'éléphant",
        "content": "L'éléphant s'est échappé",
    },
    {
        "id": "9d24a2b7-757e-4331-8922-06c587ac219d",
        "title": "Foot",
        "content": "Le foot est un sport populaire",
    },
    {
        "id": "7f55163b-4195-4334-9218-53cfc2557ea7",
        "title": "Il va courir",
        "content": "Il va courir",
    },
]
