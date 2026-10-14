from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [("activities", "0002_participant_enrollment"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AddField(model_name="participant", name="user", field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="participant", to=settings.AUTH_USER_MODEL)),
        migrations.CreateModel(name="Token", fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("digest", models.CharField(max_length=64, unique=True)), ("kind", models.CharField(max_length=8)), ("expires_at", models.DateTimeField()), ("revoked_at", models.DateTimeField(blank=True, null=True)), ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL))]),
        migrations.CreateModel(name="ServiceKey", fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("digest", models.CharField(max_length=64, unique=True)), ("name", models.CharField(max_length=100)), ("created_at", models.DateTimeField(auto_now_add=True))]),
    ]
