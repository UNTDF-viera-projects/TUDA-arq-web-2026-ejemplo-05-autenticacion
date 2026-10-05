"""Retira tablas ajenas al mecanismo de sesión sin reescribir el historial."""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("activities", "0003_auth")]
    operations = [migrations.DeleteModel(name="Token"), migrations.DeleteModel(name="ServiceKey")]
