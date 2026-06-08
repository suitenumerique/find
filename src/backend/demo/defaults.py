"""Parameters that define how the demo site will be built."""

NB_OBJECTS = {"documents": 1000, "services": 5}

DEV_SERVICES = (
    {
        "slug": "docs",
        "name": "Docs",
        "client_id": "impress",
        "token": "find-api-key-for-docs-with-exactly-50-chars-length",
    },
    {
        "slug": "drive",
        "name": "Drive",
        "client_id": "drive",
        "token": "find-api-key-for-driv-with-exactly-50-chars-length",
    },
    {
        "slug": "conversations",
        "name": "Conversations",
        "client_id": "conversations",
        "token": "find-api-key-for-conv-with-exactly-50-chars-length",
    },
)
