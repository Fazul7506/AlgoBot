from django.core.management.base import BaseCommand, CommandError

from apps.ai_engine.training import MarketModelTrainer


class Command(BaseCommand):
    help = "Train validated AI market models from persisted OHLC candles."

    def add_arguments(self, parser):
        parser.add_argument("--symbol", help="Train one market symbol")
        parser.add_argument("--timeframe", default="M1")
        parser.add_argument("--min-accuracy", type=float, default=0.52)

    def handle(self, *args, **options):
        trainer = MarketModelTrainer()
        try:
            if options["symbol"]:
                result = trainer.train_symbol(options["symbol"], options["timeframe"], options["min_accuracy"])
            else:
                result = trainer.train_active_symbols(options["timeframe"], options["min_accuracy"])
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS("AI training completed."))
        self.stdout.write(str(result))
