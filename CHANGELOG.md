# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

# Unreleased

## Added

- ✨(backend) add semantic search
- backend application
- helm chart
- 🐛(backend) fix missing index creation in 'index/' view
- ✨(backend) allow indexation of documents with either empty content or title.
- ✨(api) new fulltext 'search/' view with OIDC resource server authentication
- ✨(backend) limit access to documents : public & authenticated with a
              linkreach & owned ones
- ✨(backend) limit search to the calling app (audience) and a configured
              list of services
