"""Parameters that define how the demo site will be built."""

NB_OBJECTS = {"documents": 1000, "services": 5}

DEV_SERVICES = (
    {
        "name": "docs",
        "client_id": "impress",
        "token": "find-api-key-for-docs",
    },
    {
        "name": "drive",
        "client_id": "drive",
        "token": "find-api-key-for-drive",
    },
    {
        "name": "conversations",
        "client_id": "conversations",
        "token": "find-api-key-for-conversations",
    },
)
