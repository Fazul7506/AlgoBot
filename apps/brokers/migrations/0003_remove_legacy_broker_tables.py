from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("brokers", "0002_canonicalize_legacy_broker_data")]

    # Legacy tables must remain available until execution, portfolio, and
    # strategy foreign keys have been remapped to canonical brokers models.
    # The actual removal is performed by brokers.0005 after those migrations.
    operations = []
