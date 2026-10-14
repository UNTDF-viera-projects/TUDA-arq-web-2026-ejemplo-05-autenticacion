"""Modelos del catálogo y de la única credencial de este ejemplo."""
import uuid

from django.conf import settings
from django.db import models


class Activity(models.Model):
    """Actividad del catálogo con un número máximo de inscripciones."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=160)
    starts_at = models.DateTimeField()
    capacity = models.PositiveIntegerField()

    class Meta:
        ordering = ("starts_at",)
        verbose_name_plural = "activities"

    def __str__(self):
        """Devuelve el título para herramientas de Django y depuración."""
        return self.title


class Participant(models.Model):
    """Perfil de la persona asociado a su cuenta Django."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.CASCADE, related_name="participant",
    )

    class Meta:
        verbose_name_plural = "participants"

    def __str__(self):
        """Devuelve el nombre de la persona como etiqueta legible."""
        return self.name


class Enrollment(models.Model):
    """Relación única entre participante y actividad; define su propietario."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name="enrollments")
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name="enrollments")
    enrolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "enrollments"
        constraints = [models.UniqueConstraint(fields=("participant", "activity"), name="unique_enrollment")]


class Token(models.Model):
    """Hash de bearer opaco: jamás conserva el secreto recibido por el cliente."""

    digest = models.CharField(max_length=64, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
