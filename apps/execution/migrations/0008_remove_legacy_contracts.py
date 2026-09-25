from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("execution", "0007_brokertradehistory")]
    operations = [migrations.RunSQL("DROP TABLE IF EXISTS contracts_contract", migrations.RunSQL.noop)]
