"""Helper command to test Albert AI features"""

from mimetypes import guess_type
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.services.albert import AlbertAI, AlbertAIError


class Command(BaseCommand):
    """A management command to test Albert AI features"""

    help = __doc__

    def add_arguments(self, parser):
        """Command arguments."""
        subparsers = parser.add_subparsers(help="sub-command help", dest="action")

        parse = subparsers.add_parser("parse", help="parse help")
        parse.add_argument(nargs="+", dest="files")
        parse.add_argument(
            "-f", "--format", dest="format", default="markdown", help="output format"
        )
        parse.add_argument(
            "-p", "--pages", dest="page", default="", help="extracted pages"
        )

    def handle(self, *args, **options):
        """Handling of the management command."""
        action = options.get("action")

        try:
            handler = getattr(self, f"handle_{action}")
        except AttributeError:
            self.print_help("albert", action)
            return

        handler(options)

    def handle_parse(self, options):
        """Handling of the file convertion using Albert AI (only pdf)"""
        paths = [Path(p) for p in options.get("files", [])]
        albert = AlbertAI()

        for path in paths:
            with open(path, "rb") as fd:
                try:
                    self.stdout.write(
                        albert.convert(
                            content=fd,
                            mimetype=guess_type(path)[0],
                            output=options.get("format"),
                            pages=options.get("pages"),
                        )
                    )
                except AlbertAIError as e:
                    raise CommandError(f"Unable to convert {path} : {e.message}") from e
