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

- 🐛(index) report re-indexed documents as successes in bulk #194
- 🐛(index) answer 207 when OpenSearch fails some documents of a bulk
- 🐛(search) sort by title across languages #175
- 🐛(delete) delete every matching document, not only the first 10 #174
- 🐛(delete) delete nothing, instead of failing, for a service without index
- 🔒️(services) store service tokens hashed
- 🔒️(ci) restrict GITHUB_TOKEN permissions in workflows
- 🔒️(dependencies) upgrade vulnerable transitive dependencies
- 🐛(demo) scope demo indices and their deletion to the index prefix
- 🐛(index) refuse non-object documents and accept empty bulks, not a 500

## Added

- ✨(services) look up services by token from async code
- ✨(menshen) authenticate user tokens with Menshen introspection
- ✨(admin) show service tokens once, with a copy button
- ✨(scopes) select indices from Menshen find scopes
- 🔧(menshen) document and check a local Menshen for Find
- ✅(tests) restore search, access-control and single indexing tests
- 📝(adr) accept async django-ninja and Menshen authentication
- 🎉(project) Initial release
