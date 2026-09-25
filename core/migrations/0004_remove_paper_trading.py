from django.db import migrations


def remove_legacy_paper_tables(apps, schema_editor):
    schema_editor.execute("DROP TABLE IF EXISTS paper_trading_papertrade")
    schema_editor.execute("DROP TABLE IF EXISTS paper_trading_paperaccount")


class Migration(migrations.Migration):
    dependencies = [("core", "0003_alter_payment_currency_and_more")]
    operations = [
        migrations.RemoveField(model_name="botsettings", name="is_paper_trading"),
        migrations.RemoveField(model_name="botsettings", name="paper_balance"),
        migrations.RunPython(remove_legacy_paper_tables, migrations.RunPython.noop),
    ]
