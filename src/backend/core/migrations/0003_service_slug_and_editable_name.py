import re

import django.core.validators
from django.db import migrations, models


def backfill_slug_from_name(apps, schema_editor):
    Service = apps.get_model("core", "Service")  # noqa: N806
    seen = set()
    for service in Service.objects.all():
        derived = re.sub(r"[^a-zA-Z0-9]", "", service.name or "").lower()
        if not derived:
            raise RuntimeError(
                f"Cannot derive slug for Service id={service.pk!r} "
                f"name={service.name!r}: name contains no alphanumeric characters."
            )
        if derived in seen:
            raise RuntimeError(
                f"Slug collision while backfilling: name={service.name!r} -> "
                f"slug={derived!r} already used by another service."
            )
        seen.add(derived)
        service.slug = derived
        service.save(update_fields=["slug"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_service_client_id_service_services"),
    ]

    operations = [
        migrations.AddField(
            model_name="service",
            name="slug",
            field=models.CharField(max_length=20, null=True),
        ),
        migrations.RunPython(
            backfill_slug_from_name,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
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
