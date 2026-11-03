# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

## Changed

- 📝(docs) rewrite the architecture documentation #186
- 🚀(deploy) serve Find over ASGI with uvicorn
- ⚡️(static) serve static files with the async ServeStatic
- 💥(api) serve the endpoints with async django-ninja instead of DRF
- 💥(api) authenticate search and delete with Menshen-exchanged tokens
- 💥(api) select the searched and deleted services from Menshen scopes
- ➖(dependencies) remove DRF, drf-spectacular and the OIDC resource server
- ⬆️(dependencies) introspect tokens with menshen-client 0.3.0 async client
- 💥(search) return a stable response contract instead of raw hits #179
- ⚡️(search) query OpenSearch with an async client
- ⚡️(delete) delete documents with the async OpenSearch client
- ⚡️(index) index documents with the async OpenSearch client

## Removed

- 🔥(celery) remove Celery, which ran no task #183
- 🔥(services) remove the client id and allowed services of a service

## Fixed

- 🐛(helm) render the helmfile templates with helmfile v1
- 🐛(tilt) rebuild the image when the dependencies change
- 🔒️(settings) remove CORS, not needed by a server-to-server API #177
- 🐛(search) restrict the search to the requested services #172
- 🐛(delete) delete from the index of the requested service only #173
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

- ✨(api) add the django-ninja API, its error handling and documentation
- ✨(services) look up services by token from async code
- ✨(menshen) authenticate user tokens with Menshen introspection
- ✨(admin) show service tokens once, with a copy button
- ✨(scopes) select indices from Menshen find scopes
- 🔧(menshen) document and check a local Menshen for Find
- ✅(tests) restore search, access-control and single indexing tests
- 📝(adr) accept async django-ninja and Menshen authentication
- 🎉(project) Initial release
