"""Queries and expected document IDs for evaluation in French language."""

queries = [
    {
        "q": "elephant",
        "expected_document_ids": [23, 74],
    },
    {
        "q": "courir",
        "expected_document_ids": [76],
    },
    {
        # test "football"  -> "foot"
        "q": "football",
        "expected_document_ids": [75],
    },
    {  # test partial word matching
        "q": "couri",
        "expected_document_ids": [76],
    },
    {
        # test fuzzy matching with ngrams
        "q": "courrir",
        "expected_document_ids": [76],
    },
]
