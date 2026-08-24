from django.core.management.base import BaseCommand
import asyncio

from trading.bot_engine import BrokerBotEngine
from django.contrib.auth.models import User
from asgiref.sync import sync_to_async
from apps.brokers.models import BrokerAccount


class Command(BaseCommand):
    def __init__(self):
        super().__init__()
        self.tasks = set()
        self.running = True

    def handle(self, *args, **kwargs):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.run_all_users())
        finally:
            loop.close()

    def shutdown(self):
        self.stdout.write(self.style.WARNING("Shutting down bot manager..."))
        self.running = False
        for task in self.tasks:
            task.cancel()

    async def run_all_users(self):
        users = await sync_to_async(list)(User.objects.all())
        if not users:
            self.stdout.write(self.style.ERROR("No users found in database"))
            return
        self.stdout.write(self.style.SUCCESS(f"Starting bot for {len(users)} users"))
        for user in users:
            engine = BrokerBotEngine()
            task = asyncio.create_task(self.run_engine(engine, user), name=f"user_engine_{user.id}")
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def run_engine(self, engine, user):
        try:
            token = await self._get_token(user)
            if not token:
                self.stdout.write(self.style.WARNING(f"No active canonical broker credential for user {user.id}; engine not started."))
                return
            await engine.connect({"user_id": user.id, "access_token": token})
            await engine.stream_ticks()
        except asyncio.CancelledError:
            self.stdout.write(self.style.WARNING(f"Engine cancelled for user {user.id}"))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"Bot crashed for user {user.id}: {str(exc)}"))

    async def _get_token(self, user):
        account = await sync_to_async(
            lambda: BrokerAccount.objects.select_related("broker").filter(
                user=user,
                is_preferred=True,
                status="active",
                broker__status="active",
            ).order_by("id").first()
        )()
        if not account:
            return ""
        return await sync_to_async(account.get_access_token)()
