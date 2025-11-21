queries = [
    {
        "q": "cours d'histoire de l'antiquité",
        "expected_document_ids": [5, 8],
    },
    {
        "q": "recette salée végétarienne",
        "expected_document_ids": [42, 54, 58],
    },
    {
        "q": "art dramatique",
        "expected_document_ids": [71],
    },
    {
        "q": "art de bouger son corps",
        "expected_document_ids": [63, 68],
    },
    {
        "q": "mammifères aquatiques",
        "expected_document_ids": [22, 37],
    },
    {
        "q": "insectes pollinisateurs",
        "expected_document_ids": [29],
    },
    {
        "q": "prédateur félin",
        "expected_document_ids": [21, 30],
    },
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
