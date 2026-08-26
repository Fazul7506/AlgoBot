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
                self.stdout.write(self.style.SUCCESS("AI model training completed for the requested symbol."))
                self.stdout.write(str(result))
                return

            result = trainer.train_active_symbols(options["timeframe"], options["min_accuracy"])
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        total = len(result)
        trained = sum(1 for value in result.values() if value.get("status") != "skipped")
        skipped = total - trained
        self.stdout.write("AI TRAINING SUMMARY")
        self.stdout.write("===================")
        self.stdout.write(f"Symbols requested: {total}")
        self.stdout.write(f"Successfully trained: {trained}")
        self.stdout.write(f"Skipped/failed: {skipped}")
        if trained == 0:
            self.stdout.write(self.style.WARNING(
                "NO AI MODELS WERE UPDATED. Historical OHLC data is missing or no model passed validation."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(f"AI training produced validated models for {trained}/{total} symbols."))
        self.stdout.write(str(result))
