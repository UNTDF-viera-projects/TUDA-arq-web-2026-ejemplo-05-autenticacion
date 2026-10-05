"""Dominio de actividades e inscripciones, sin otros modelos de credenciales."""
import uuid
from django.conf import settings
from django.db import models


class Activity(models.Model):
    """Actividad con cupo compartido por sus participantes."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=160)
    starts_at = models.DateTimeField()
    capacity = models.PositiveIntegerField()

    class Meta:
        ordering = ("starts_at",)
        verbose_name_plural = "activities"

    def __str__(self):
        """Devuelve el título legible en formularios y herramientas Django."""
        return self.title


class Participant(models.Model):
    """Persona de dominio vinculada con la cuenta de la sesión verificada."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="participant")

    class Meta:
        verbose_name_plural = "participants"

    def __str__(self):
        """Muestra un nombre legible sin exponer credenciales."""
        return self.name


class Enrollment(models.Model):
    """Inscripción única de una persona en una actividad."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name="enrollments")
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name="enrollments")
    enrolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "enrollments"
        constraints = [models.UniqueConstraint(fields=("participant", "activity"), name="unique_enrollment")]
