from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('strategies', '0002_strategyconfiguration_control_state')]

    operations = [
        migrations.AlterField(
            model_name='strategyexecution',
            name='signal',
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
        migrations.AlterField(
            model_name='strategyexecution',
            name='confidence',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True),
        ),
        migrations.AlterField(
            model_name='strategysignal',
            name='signal',
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
        migrations.AlterField(
            model_name='strategysignal',
            name='confidence',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True),
        ),
    ]
