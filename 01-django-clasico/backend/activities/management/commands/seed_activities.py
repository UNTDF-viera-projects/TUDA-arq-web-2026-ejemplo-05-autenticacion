from datetime import datetime
from uuid import UUID
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone
from activities.models import Activity, Participant

ACTIVITIES = [
    ("1b470ddf-3e84-4b77-9aae-091d21e52bd6", "Introducción a APIs web", datetime(2026, 3, 23, 18), 30),
    ("6ccaf64f-d37e-4e6c-ae03-f3d6547bb297", "Contratos HTTP observables", datetime(2026, 3, 25, 18), 24),
    ("80c08526-3da1-4f0a-845c-740fa33f1f50", "Taller de integración", datetime(2026, 3, 27, 17), 20),
]
class Command(BaseCommand):
    """Carga datos repetibles sin cambiar contraseñas de cuentas existentes."""
    help = "Carga actividades y dos cuentas de demostración (01 a 05)."
    def handle(self, *args, **options):
        """Crea actividades fijas y dos participantes, sin duplicarlos."""
        for id_, title, starts, capacity in ACTIVITIES:
            Activity.objects.update_or_create(id=UUID(id_), defaults={"title": title, "starts_at": timezone.make_aware(starts), "capacity": capacity})
        for email, name in [("demo@example.com", "Demo"), ("other@example.com", "Otra persona")]:
            user, created = get_user_model().objects.get_or_create(username=email, defaults={"email": email})
            if created:
                user.set_password("Demo12345!")
                user.save()
            Participant.objects.get_or_create(user=user, defaults={"name": name})
        self.stdout.write(self.style.SUCCESS("Actividades y cuentas de demostración listas."))
