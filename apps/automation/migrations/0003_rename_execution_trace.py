from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("automation", "0002_automationevent_user"),
    ]

    operations = [
        migrations.RenameField(
            model_name="workflowexecution",
            old_name="audit_log",
            new_name="execution_trace",
        ),
    ]
