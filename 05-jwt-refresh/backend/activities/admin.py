from django.contrib import admin

from .models import Activity, Enrollment, Participant


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    """Presenta actividad y cupo si se habilita administración en otra configuración."""
    list_display = ("title", "starts_at", "capacity", "id")
    ordering = ("starts_at",)


@admin.register(Participant)
class ParticipantAdmin(admin.ModelAdmin):
    """Presenta perfiles sin datos de autenticación."""
    list_display = ("name", "id")


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    """Permite inspeccionar la relación entre participantes y actividades."""
    list_display = ("participant", "activity", "enrolled_at", "id")
    ordering = ("enrolled_at",)
