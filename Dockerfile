# Django find

# ---- base image to inherit from ----
FROM python:3.12-slim-bookworm AS base

# Upgrade system packages to install security updates
RUN apt-get update && \
  apt-get -y upgrade && \
  rm -rf /var/lib/apt/lists/*

# ---- Back-end builder image ----
FROM base AS back-builder

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Disable Python downloads, because we want to use the system interpreter
# across both images. If using a managed Python version, it needs to be
# copied from the build image into the final image;
ENV UV_PYTHON_DOWNLOADS=0

# install uv
COPY --from=ghcr.io/astral-sh/uv:0.9.10 /uv /uvx /bin/

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

# Install libpangocairo & rdfind
RUN apt-get update && \
    apt-get install -y \
      libpangocairo-1.0-0 \
      rdfind && \
    rm -rf /var/lib/apt/lists/*

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
RUN apt-get update && \
    apt-get install -y \
      gettext \
      libcairo2 \
      libffi-dev \
      libgdk-pixbuf2.0-0 \
      libpango-1.0-0 \
      libpangocairo-1.0-0 \
      shared-mime-info && \
  rm -rf /var/lib/apt/lists/*

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
RUN apt-get update && \
    apt-get install -y postgresql-client && \
    rm -rf /var/lib/apt/lists/*

# Install development dependencies
RUN --mount=from=ghcr.io/astral-sh/uv:0.9.10,source=/uv,target=/bin/uv \
    uv sync --locked --all-extras

# Restore the un-privileged user running the application
ARG DOCKER_USER
USER ${DOCKER_USER}

# Target database host (e.g. database engine following docker compose services
# name) & port
ENV DB_HOST=postgresql \
    DB_PORT=5432

# Run django development server
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# ---- Production image ----
FROM core AS backend-production

ARG FIND_STATIC_ROOT=/data/static

# Gunicorn
RUN mkdir -p /usr/local/etc/gunicorn
COPY docker/files/usr/local/etc/gunicorn/find.py /usr/local/etc/gunicorn/find.py

# Un-privileged user running the application
ARG DOCKER_USER
USER ${DOCKER_USER}

# Copy statics
COPY --from=link-collector ${FIND_STATIC_ROOT} ${FIND_STATIC_ROOT}

# The default command runs gunicorn WSGI server in find's main module
CMD ["gunicorn", "-c", "/usr/local/etc/gunicorn/find.py", "find.wsgi:application"]
