"""Conserva dominio e historial, retira claves y access opacos de la versión mezclada."""
from django.db import migrations


def retain_refresh(apps, schema_editor):
    """Solo los hashes refresh históricos pertenecen al mecanismo actual."""
    apps.get_model("activities", "Token").objects.exclude(kind="refresh").delete()


class Migration(migrations.Migration):
    dependencies = [("activities", "0003_auth")]
    operations = [
        migrations.RunPython(retain_refresh, migrations.RunPython.noop),
        migrations.DeleteModel(name="ServiceKey"),
        migrations.RenameModel(old_name="Token", new_name="RefreshToken"),
        migrations.RemoveField(model_name="refreshtoken", name="kind"),
    ]
