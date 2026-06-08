import django.core.validators
from django.db import migrations, models


def wipe_services(apps, schema_editor):
    """Drop pre-existing services before introducing the required ``slug`` column.

    No production data exists, so there is no value-preserving backfill to do.
    Wiping ``Service`` rows up front lets ``AddField`` introduce ``slug`` with
    its final ``NOT NULL UNIQUE`` shape in a single operation. Going through
    the ORM cascades to the ``services`` self-referential M2M join table.
    """
    Service = apps.get_model("core", "Service")  # noqa: N806
    Service.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_service_client_id_service_services"),
    ]

    operations = [
        migrations.RunPython(
            wipe_services,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AddField(
            model_name="service",
            name="slug",
            field=models.SlugField(
                editable=False,
                help_text=(
                    "Stable identifier used in the OpenSearch index name. "
                    "Lowercase alphanumeric only. Set on creation, immutable thereafter."
                ),
                max_length=20,
                unique=True,
                validators=[
                    django.core.validators.RegexValidator(
                        message="Slug must contain only lowercase letters and digits.",
                        regex="^[a-z0-9]+$",
                    )
                ],
            ),
        ),
        migrations.AlterField(
            model_name="service",
            name="name",
            field=models.CharField(max_length=255),
        ),
        migrations.AddConstraint(
            model_name="service",
            constraint=models.CheckConstraint(
                condition=models.Q(("slug__regex", "^[a-z0-9]+$")),
                name="slug_alphanumeric_only",
            ),
        ),
    ]
