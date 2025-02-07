# Find

Find can index documents from several applications sharing a common OIDC federation
and allows users to search documents with their access rights accross all applications
in the federation.

Find is built on top of [Django Rest
Framework](https://www.django-rest-framework.org/).

## Getting started

### Prerequisite

Make sure you have a recent version of Docker and [Docker
Compose](https://docs.docker.com/compose/install) installed on your laptop:

```bash
$ docker -v
  Docker version 27.4.1, build b9d17ea

$ docker compose version
  Docker Compose version v2.32.1
```

> ⚠️ You may need to run the following commands with `sudo` but this can be
> avoided by assigning your user to the `docker` group. See docker 
> [Documentation](https://docs.docker.com/engine/install/linux-postinstall/)

### Project bootstrap

The easiest way to start working on the project is to use GNU Make:

```bash
$ make bootstrap
```

This command builds the `app` container, installs dependencies, performs
database migrations and compile translations. It's a good idea to use this
command each time you are pulling code from the project repository to avoid
dependency-releated or migration-releated issues.

Your Docker services should now be up and running 🎉

### Adding content

You can create a basic demo site by running:

    $ make demo

Finally, you can check all available Make rules using:

```bash
$ make help
```

### Django admin

You can access the Django admin site at
[http://localhost:8071/admin](http://localhost:8071/admin).

You first need to create a superuser account:

```bash
$ make superuser
```

## Contributing

This project is intended to be community-driven, so please, do not hesitate to
get in touch if you have any question related to our implementation or design
decisions.

## License

This work is released under the MIT License (see [LICENSE](./LICENSE)).
