"""Retira credenciales ajenas sin modificar el historial ya aplicado."""
from django.db import migrations


def discard_foreign_tokens(apps, schema_editor):
    """Descarta tokens históricos que no eran access opacos de este ejemplo."""
    apps.get_model("activities", "Token").objects.exclude(kind="access").delete()


class Migration(migrations.Migration):
    dependencies = [("activities", "0003_auth")]
    operations = [
        migrations.RunPython(discard_foreign_tokens, migrations.RunPython.noop),
        migrations.RemoveField(model_name="token", name="kind"),
        migrations.DeleteModel(name="ServiceKey"),
    ]
