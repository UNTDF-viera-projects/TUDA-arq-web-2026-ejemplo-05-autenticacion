import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Activity",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("title", models.CharField(max_length=160)),
                ("starts_at", models.DateTimeField()),
                ("capacity", models.PositiveIntegerField()),
            ],
            options={
                "verbose_name_plural": "activities",
                "ordering": ("starts_at",),
            },
        ),
    ]
