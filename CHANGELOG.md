# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

## Changed

- 💥(search) return a stable response contract instead of raw hits #179
- ⚡️(search) query OpenSearch with an async client
- ⚡️(delete) delete documents with the async OpenSearch client
- ⚡️(index) index documents with the async OpenSearch client

## Fixed

- 🐛(delete) delete every matching document, not only the first 10 #174
- 🔒️(services) store service tokens hashed
- 🔒️(ci) restrict GITHUB_TOKEN permissions in workflows
- 🔒️(dependencies) upgrade vulnerable transitive dependencies
- 🐛(demo) scope demo indices and their deletion to the index prefix

## Added

- ✨(admin) show service tokens once, with a copy button
- ✨(scopes) select indices from Menshen find scopes
- 🔧(menshen) document and check a local Menshen for Find
- ✅(tests) restore search, access-control and single indexing tests
- 📝(adr) accept async django-ninja and Menshen authentication
- 🎉(project) Initial release
