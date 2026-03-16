"""Queries and expected document IDs for evaluation in French language."""

queries = [
    {
        "q": "elephant",
        "expected_document_ids": ["sc-23", "ft-1"],
    },
    {
        "q": "courir",
        "expected_document_ids": ["ft-3"],
    },
    {
        # test "football"  -> "foot"
        "q": "football",
        "expected_document_ids": ["ft-2"],
    },
    {  # test partial word matching
        "q": "couri",
        "expected_document_ids": ["ft-3"],
    },
    {
        # test fuzzy matching with ngrams
        "q": "courrir",
        "expected_document_ids": ["ft-3"],
    },
]
