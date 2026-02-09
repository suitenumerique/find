# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

# Unreleased

## Added

- ✨(backend) add semantic search
- ✨(backend) add multi-embedding and chunking
- ✨(backend) add analyzers to full-text search
- ✨(backend) handle french, english, german and dutch 
- ✨(backend) add evaluation command
- backend application
- helm chart
- ✨(backend) allow indexation of documents with either empty content or title.
- ✨(api) new fulltext 'search/' view with OIDC resource server authentication
- ✨(backend) limit access to documents : public & authenticated with a
              list of services
- 🔧(compose) rename docker network 'lasuite-net' as 'lasuite-network'
- ✨(backend) add demo service for Drive.
- ✨(backend) add OPENSEARCH_INDEX_PREFIX setting to prevent naming overlaping
              issues if the opensearch database is shared between apps.
- ✨(backend) add tags
- ✨(backend) adapt to conversation RAG
- ✨(backend) add deletion endpoint
- ✨(backend) add path filter

## Changed

- 🏗️(backend) switch Python dependency management to uv
- ✨(backend) allow deletion by tags

## Fixed

- 🐛(backend) fix missing index creation in 'index/' view
- 🐛(backend) fix parallel test execution issues
