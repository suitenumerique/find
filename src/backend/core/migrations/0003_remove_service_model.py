# Generated migration to remove Service model

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_service_client_id_service_services'),
    ]

    operations = [
        migrations.DeleteModel(
            name='Service',
        ),
    ]
