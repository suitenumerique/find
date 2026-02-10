"""Queries and expected document IDs for evaluation in French language."""

queries = [
    {
        "q": "cours d'histoire de l'antiquité",
        "expected_document_ids": ["sc-5", "sc-8"],
    },
    {
        "q": "recette salée végétarienne",
        "expected_document_ids": ["sc-42", "sc-54", "sc-58"],
    },
    {
        "q": "art dramatique",
        "expected_document_ids": ["sc-71"],
    },
    {
        "q": "art de bouger son corps",
        "expected_document_ids": ["sc-63", "sc-68"],
    },
    {
        "q": "mammifères aquatiques",
        "expected_document_ids": ["sc-22", "sc-37"],
    },
    {
        "q": "insectes pollinisateurs",
        "expected_document_ids": ["sc-29"],
    },
    {
        "q": "prédateur félin",
        "expected_document_ids": ["sc-21", "sc-30"],
    },
]
