# Django find

# ---- uv, the single place where its version is set ----
FROM ghcr.io/astral-sh/uv:0.13.7 AS uv

# ---- base image to inherit from ----
FROM python:3.14.10-alpine AS base

# Upgrade system packages to install security updates
RUN apk upgrade --no-cache

# We must do that to avoid having an outdated pip version with security issues
RUN python -m pip install --upgrade pip

# ---- Back-end builder image ----
FROM base AS back-builder

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Disable Python downloads, because we want to use the system interpreter
# across both images. If using a managed Python version, it needs to be
# copied from the build image into the final image;
ENV UV_PYTHON_DOWNLOADS=0

# install uv
COPY --from=uv /uv /uvx /bin/

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=src/backend/uv.lock,target=uv.lock \
    --mount=type=bind,source=src/backend/pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

COPY ./src/backend /app

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# ---- static link collector ----
FROM base AS link-collector
ARG FIND_STATIC_ROOT=/data/static

# Install rdfind
RUN apk add --no-cache rdfind

# Copy the application from the builder
COPY --from=back-builder /app /app

ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# collectstatic
RUN DJANGO_CONFIGURATION=Build \
    DJANGO_JWT_PRIVATE_SIGNING_KEY=Dummy \
    OPENSEARCH_PASSWORD=Dummy \
    python manage.py collectstatic --noinput

# Replace duplicated file by a symlink to decrease the overall size of the
# final image
RUN rdfind -makesymlinks true -followsymlinks true -makeresultsfile false ${FIND_STATIC_ROOT}

# ---- Core application image ----
FROM base AS core

ENV PYTHONUNBUFFERED=1

# Install required system libs
RUN apk add --no-cache gettext

# Copy entrypoint
COPY ./docker/files/usr/local/bin/entrypoint /usr/local/bin/entrypoint

# Give the "root" group the same permissions as the "root" user on /etc/passwd
# to allow a user belonging to the root group to add new users; typically the
# docker user (see entrypoint).
RUN chmod g=u /etc/passwd

# Copy the prepared application (see .dockerignore)
COPY --from=back-builder /app /app

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH"

# We wrap commands run in this container by the following entrypoint that
# creates a user on-the-fly with the container user ID (see USER) and root group
# ID.
ENTRYPOINT [ "/usr/local/bin/entrypoint" ]

# ---- Development image ----
FROM core AS backend-development

# Switch back to the root user to install development dependencies
USER root:root

# Install psql
RUN apk add --no-cache postgresql-client

# Install development dependencies
RUN --mount=from=uv,source=/uv,target=/bin/uv \
    uv sync --locked --all-extras

# Restore the un-privileged user running the application
ARG DOCKER_USER
USER ${DOCKER_USER}

# Target database host (e.g. database engine following docker compose services
# name) & port
ENV DB_HOST=postgresql \
    DB_PORT=5432

# Run the uvicorn ASGI server, reloading it when the code changes
CMD [\
  "uvicorn",\
  "--host=0.0.0.0",\
  "--port=8000",\
  "--reload",\
  "--reload-dir=/app",\
  "--lifespan=off",\
  "find.asgi:application"\
]

# ---- Production image ----
FROM core AS backend-production

# pip is not needed at runtime (the dependencies are installed with uv)
RUN /usr/local/bin/python -m pip uninstall --yes pip

ARG FIND_STATIC_ROOT=/data/static

# Un-privileged user running the application
ARG DOCKER_USER
USER ${DOCKER_USER}

# Copy statics
COPY --from=link-collector ${FIND_STATIC_ROOT} ${FIND_STATIC_ROOT}

# The default command runs uvicorn ASGI server in find's main module
# WEB_CONCURRENCY: number of workers to run <=> --workers=2
# Each worker restarts after 20000 to 40000 requests: the jitter staggers the
# restarts, so that the other workers keep accepting requests
ENV WEB_CONCURRENCY=2
CMD [\
  "uvicorn",\
  "--host=0.0.0.0",\
  "--port=8000",\
  "--proxy-headers",\
  "--timeout-graceful-shutdown=90",\
  "--limit-max-requests=20000",\
  "--limit-max-requests-jitter=20000",\
  "--lifespan=off",\
  "find.asgi:application"\
]
