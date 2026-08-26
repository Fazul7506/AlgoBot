from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    help = "Create and apply migrations for the AI engine."

    def handle(self, *args, **options):
        call_command("makemigrations", "ai_engine")
        call_command("migrate", "ai_engine")
        self.stdout.write(self.style.SUCCESS("AI engine migrations created/applied."))
