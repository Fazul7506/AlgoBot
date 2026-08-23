from django.db import migrations


# A previous production deployment contained a transient 0004 migration that
# renamed an execution index which was already absent on some databases. This
# repair migration is deliberately newer than that historical migration so it
# still runs when the old 0004 is present in django_migrations, while remaining
# harmless on clean databases.
REPAIR_INDEXES = """
DROP INDEX IF EXISTS strategies_s_enabled_51dc7f_idx;
DROP INDEX IF EXISTS strategies_s_slug_4f00a6_idx;

CREATE INDEX IF NOT EXISTS strategies__enabled_aaadb9_idx
    ON strategies_strategy (enabled, category);
CREATE INDEX IF NOT EXISTS strategies__slug_e97c02_idx
    ON strategies_strategy (slug, version);
CREATE INDEX IF NOT EXISTS strategies__user_id_90ced2_idx
    ON strategies_strategyconfiguration (user_id, enabled);
CREATE INDEX IF NOT EXISTS strategies__symbol_48d2fd_idx
    ON strategies_strategyconfiguration (symbol, timeframe);
CREATE INDEX IF NOT EXISTS strategies__strateg_47d2d1_idx
    ON strategies_strategyexecution (strategy_id, status);
CREATE INDEX IF NOT EXISTS strategies__symbol_5d51cd_idx
    ON strategies_strategyexecution (symbol, timeframe, started_at DESC);
CREATE INDEX IF NOT EXISTS strategies__strateg_802884_idx
    ON strategies_strategysignal (strategy_id, symbol, timestamp DESC);
"""


class Migration(migrations.Migration):
    dependencies = [
        ("strategies", "0003_use_canonical_broker_account"),
    ]

    atomic = False

    operations = [
        migrations.RunSQL(
            sql=REPAIR_INDEXES,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
