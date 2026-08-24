"""Management command to initialize database and create required data."""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from core.models import UserProfile, Subscription, BotSettings


class Command(BaseCommand):
    help = 'Initialize database with required data'

    def handle(self, *args, **options):
        """Run initialization"""
        self.stdout.write(self.style.SUCCESS('Starting database initialization...'))
        
        # Ensure all users have related profiles
        for user in User.objects.all():
            UserProfile.objects.get_or_create(user=user)
            Subscription.objects.get_or_create(user=user)
            BotSettings.objects.get_or_create(user=user)
            self.stdout.write(f'✓ Initialized {user.username}')
        
        self.stdout.write(self.style.SUCCESS('Database initialization complete!'))
