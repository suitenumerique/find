"""Queries and expected document IDs for evaluation in French language."""

queries = [
    {
        "q": "elephant",
        "expected_document_ids": [
            "3aedda66-aeff-4291-a21d-0bd0303d0ee2",
            "456a071a-d433-47f3-a398-b95db6657841",
        ],
    },
    {
        "q": "courir",
        "expected_document_ids": ["7f55163b-4195-4334-9218-53cfc2557ea7"],
    },
    {
        # test "football"  -> "foot"
        "q": "football",
        "expected_document_ids": ["9d24a2b7-757e-4331-8922-06c587ac219d"],
    },
    {  # test partial word matching
        "q": "couri",
        "expected_document_ids": ["7f55163b-4195-4334-9218-53cfc2557ea7"],
    },
    {
        # test fuzzy matching with ngrams
        "q": "courrir",
        "expected_document_ids": ["7f55163b-4195-4334-9218-53cfc2557ea7"],
    },
]
