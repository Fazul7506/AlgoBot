from django.db import migrations


def remove_legacy_paper_brokers(apps, schema_editor):
    Broker = apps.get_model("brokers", "Broker")
    for broker in Broker.objects.filter(broker_type="paper"):
        broker.delete()


class Migration(migrations.Migration):
    dependencies = [("brokers", "0005_remove_preferred_account")]
    operations = [migrations.RunPython(remove_legacy_paper_brokers, migrations.RunPython.noop)]
