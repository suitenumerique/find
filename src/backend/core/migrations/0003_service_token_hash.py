import hashlib

from django.db import migrations, models


def hash_tokens(apps, schema_editor):
    """Replace the plaintext tokens by their hash, keeping existing tokens valid."""
    Service = apps.get_model("core", "Service")
    for service in Service.objects.all():
        service.token_hash = hashlib.sha256(service.token.encode()).hexdigest()
        service.save(update_fields=["token_hash"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_service_client_id_service_services"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="service",
            name="token_length_exact_50",
        ),
        migrations.AddField(
            model_name="service",
            name="token_hash",
            field=models.CharField(editable=False, max_length=64, null=True),
        ),
        # Irreversible: plaintext tokens cannot be recovered from their hash
        migrations.RunPython(hash_tokens),
        migrations.RemoveField(
            model_name="service",
            name="token",
        ),
        migrations.AlterField(
            model_name="service",
            name="token_hash",
            field=models.CharField(editable=False, max_length=64, unique=True),
        ),
    ]
