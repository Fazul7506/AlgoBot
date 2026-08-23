from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("trading", "0005_alter_derivaccount_options_derivaccount_account_type_and_more"),
        ("brokers", "0003_remove_legacy_broker_tables"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[migrations.DeleteModel(name="DerivAccount")],
        ),
    ]
