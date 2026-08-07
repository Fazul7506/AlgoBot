from django.core.management.base import BaseCommand
import asyncio
import signal

from trading.bot_engine import BrokerBotEngine
from django.contrib.auth.models import User
from asgiref.sync import sync_to_async


class Command(BaseCommand):

    def __init__(self):
        super().__init__()
        self.tasks = set()
        self.running = True

    # --------------------------------------------------
    # ENTRY POINT
    # --------------------------------------------------
    def handle(self, *args, **kwargs):

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            loop.run_until_complete(self.run_all_users())
        finally:
            loop.close()

    # --------------------------------------------------
    # SHUTDOWN HANDLER
    # --------------------------------------------------
    def shutdown(self):
        self.stdout.write(self.style.WARNING("Shutting down bot manager..."))
        self.running = False

        for task in self.tasks:
            task.cancel()

    # --------------------------------------------------
    # LOAD USERS + START ENGINES
    # --------------------------------------------------
    async def run_all_users(self):

        users = await sync_to_async(list)(User.objects.all())

        if not users:
            self.stdout.write(self.style.ERROR("No users found in database"))
            return

        self.stdout.write(
            self.style.SUCCESS(f"Starting bot for {len(users)} users")
        )

        for user in users:
            engine = BrokerBotEngine()

            task = asyncio.create_task(
                self.run_engine(engine, user),
                name=f"user_engine_{user.id}"
            )

            self.tasks.add(task)

            task.add_done_callback(self.tasks.discard)

        await asyncio.gather(*self.tasks, return_exceptions=True)

    # --------------------------------------------------
    # PER-USER ENGINE WRAPPER
    # --------------------------------------------------
    async def run_engine(self, engine, user):

        try:
            await engine.connect({
                "user_id": user.id,
                "access_token": await self._get_token(user)
            })

            await engine.stream_ticks()

        except asyncio.CancelledError:
            self.stdout.write(
                self.style.WARNING(f"Engine cancelled for user {user.id}")
            )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Bot crashed for user {user.id}: {str(e)}")
            )

    # --------------------------------------------------
    # SAFE DB ACCESS (TOKEN FETCH)
    # --------------------------------------------------
    async def _get_token(self, user):

        from apps.broker.models import BrokerAccount

        account = await sync_to_async(
            BrokerAccount.objects.select_related("broker").get
        )(user=user, is_default=True)

        token = await sync_to_async(lambda: getattr(account, "token", None))()
        return token.get_access_token() if token else ""