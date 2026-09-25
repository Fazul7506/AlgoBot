from django.db import migrations


def remove_paper_feature_flags(apps, schema_editor):
    FeatureFlag = apps.get_model("tenants", "FeatureFlag")
    FeatureFlag.objects.filter(feature="paper_trading").delete()


class Migration(migrations.Migration):
    dependencies = [("tenants", "0001_initial")]
    operations = [migrations.RunPython(remove_paper_feature_flags, migrations.RunPython.noop)]
