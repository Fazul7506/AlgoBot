from django.db import migrations, models
import django.db.models.deletion

LEGACY_BROKER_TABLE = "broker_broker"
LEGACY_ACCOUNT_TABLE = "broker_brokeraccount"
LEGACY_TOKEN_TABLE = "broker_brokentoken"
LEGACY_LOG_TABLE = "broker_brokerconnectionlog"
LEGACY_PERMISSION_TABLE = "broker_brokerpermission"
LEGACY_DERIV_TABLE = "trading_derivaccount"

INVALID_ACCOUNT_IDS = {"", "unknown", "none", "null", "undefined", "n/a", "na"}


def _rows(cursor, table):
    cursor.execute(f'SELECT * FROM "{table}"')
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _canonical_status(value):
    value = str(value or "active").lower()
    return value if value in {"active", "disabled", "maintenance", "degraded", "offline", "coming_soon"} else "active"


def _valid_account_id(value):
    account_id = str(value or "").strip()
    return account_id if account_id.lower() not in INVALID_ACCOUNT_IDS else ""


def forwards(apps, schema_editor):
    Broker = apps.get_model("brokers", "Broker")
    BrokerAccount = apps.get_model("brokers", "BrokerAccount")
    BrokerConnectionLog = apps.get_model("brokers", "BrokerConnectionLog")
    BrokerPermission = apps.get_model("brokers", "BrokerPermission")
    db = schema_editor.connection
    tables = set(db.introspection.table_names())

    broker_map = {}
    if LEGACY_BROKER_TABLE in tables:
        with db.cursor() as cursor:
            for row in _rows(cursor, LEGACY_BROKER_TABLE):
                slug = str(row.get("slug") or row.get("name") or "legacy").lower().replace(" ", "_")
                broker_type = slug[:40]
                broker = Broker.objects.filter(broker_type=broker_type).first() or Broker.objects.filter(name=row.get("name") or slug).first()
                if broker is None:
                    broker = Broker.objects.create(
                        name=row.get("name") or slug.title(),
                        broker_type=broker_type,
                        status=_canonical_status(row.get("status")),
                        metadata={"migrated_from": "apps.broker", "legacy_id": row.get("id")},
                    )
                broker_map[row.get("id")] = broker

    if LEGACY_ACCOUNT_TABLE in tables:
        with db.cursor() as cursor:
            token_rows = {row.get("broker_account_id"): row for row in _rows(cursor, LEGACY_TOKEN_TABLE)} if LEGACY_TOKEN_TABLE in tables else {}
            for row in _rows(cursor, LEGACY_ACCOUNT_TABLE):
                broker = broker_map.get(row.get("broker_id"))
                account_id = _valid_account_id(row.get("broker_account_id"))
                if broker is None or not account_id:
                    continue
                account = BrokerAccount.objects.filter(broker=broker, account_id=account_id).first()
                # Preserve the already-canonical account when ownership is
                # ambiguous. Never overwrite another user's credentials.
                if account is not None and account.user_id != row.get("user_id"):
                    continue
                if account is None:
                    account = BrokerAccount(broker=broker, account_id=account_id, user_id=row.get("user_id"))
                account.currency = row.get("currency") or "USD"
                account.balance = row.get("balance") or 0
                account.equity = row.get("equity") or account.balance
                account.margin = row.get("margin") or 0
                account.status = "active" if row.get("is_connected") else "disabled"
                account.is_preferred = bool(row.get("is_default"))
                account.credentials = dict(account.credentials or {})
                account.credentials.setdefault("account_type", row.get("account_type") or "demo")
                token = token_rows.get(row.get("id"))
                if token:
                    account.access_token = token.get("access_token") or account.access_token
                    account.refresh_token = token.get("refresh_token") or account.refresh_token
                    account.expires_at = token.get("expires_at")
                    account.last_refresh = token.get("last_refresh")
                    account.token_status = token.get("status") or "active"
                account.save()

    if LEGACY_DERIV_TABLE in tables:
        with db.cursor() as cursor:
            for row in _rows(cursor, LEGACY_DERIV_TABLE):
                account_id = _valid_account_id(row.get("account_id"))
                if not account_id:
                    continue
                broker = Broker.objects.filter(broker_type="deriv").first()
                if broker is None:
                    broker = Broker.objects.create(name="Deriv", broker_type="deriv", status="active", supports_live=True)
                account = BrokerAccount.objects.filter(broker=broker, account_id=account_id).first()
                # A conflicting legacy owner is retained untouched. The
                # canonical row remains authoritative and deployment-safe.
                if account is not None and account.user_id != row.get("user_id"):
                    continue
                if account is None:
                    account = BrokerAccount(broker=broker, account_id=account_id, user_id=row.get("user_id"))
                account.currency = row.get("currency") or account.currency or "USD"
                account.credentials = dict(account.credentials or {})
                account.credentials.setdefault("account_type", row.get("account_type") or "demo")
                account.access_token = row.get("access_token") or account.access_token
                account.refresh_token = row.get("refresh_token") or account.refresh_token
                account.expires_at = row.get("expires_at") or account.expires_at
                account.last_refresh = row.get("last_refresh") or account.last_refresh
                account.token_status = row.get("token_status") or account.token_status
                account.status = "active"
                account.is_preferred = True
                account.save()

    if LEGACY_PERMISSION_TABLE in tables:
        with db.cursor() as cursor:
            for row in _rows(cursor, LEGACY_PERMISSION_TABLE):
                broker = broker_map.get(row.get("broker_id"))
                if broker is not None and row.get("permission"):
                    BrokerPermission.objects.update_or_create(broker=broker, permission=row["permission"], defaults={"enabled": bool(row.get("enabled", True))})

    if LEGACY_LOG_TABLE in tables:
        with db.cursor() as cursor:
            for row in _rows(cursor, LEGACY_LOG_TABLE):
                broker = broker_map.get(row.get("broker_id"))
                if broker is None:
                    continue
                account_id = _valid_account_id(row.get("broker_account_id"))
                if not account_id:
                    continue
                account = BrokerAccount.objects.filter(broker=broker, account_id=account_id).first()
                if account is None:
                    continue
                BrokerConnectionLog.objects.get_or_create(
                    broker_account=account,
                    status=row.get("status") or "unknown",
                    latency=row.get("latency"),
                    event=row.get("event") or "legacy",
                    defaults={"created_at": row.get("created_at")},
                )


def backwards(apps, schema_editor):
    raise RuntimeError("Canonical broker migration is intentionally irreversible; restore from the production backup to roll back.")


class Migration(migrations.Migration):
    dependencies = [("brokers", "0001_initial")]

    # PostgreSQL raises `cannot CREATE INDEX ... because it has pending
    # trigger events` when schema/index DDL is mixed with row-level changes
    # in the same transaction. This migration both creates canonical schema
    # and copies production rows, so it must not wrap the whole migration in
    # one transaction. Each schema operation and the data-copy operation are
    # committed independently, which also makes a retry safe after a failed
    # deployment without holding deferred trigger events open.
    atomic = False

    operations = [
        migrations.AddField("brokeraccount", "access_token", models.TextField(blank=True)),
        migrations.AddField("brokeraccount", "refresh_token", models.TextField(blank=True)),
        migrations.AddField("brokeraccount", "token_status", models.CharField(default="active", db_index=True, max_length=20)),
        migrations.AddField("brokeraccount", "expires_at", models.DateTimeField(blank=True, db_index=True, null=True)),
        migrations.AddField("brokeraccount", "last_refresh", models.DateTimeField(blank=True, null=True)),
        migrations.AddIndex("brokeraccount", models.Index(fields=["user", "token_status"], name="brokers_ba_user_tok_idx")),
        migrations.CreateModel(
            name="BrokerConnectionLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(max_length=50)),
                ("latency", models.FloatField(blank=True, null=True)),
                ("event", models.CharField(max_length=120)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("broker_account", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="connection_logs", to="brokers.brokeraccount")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="BrokerPermission",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("permission", models.CharField(max_length=80)),
                ("enabled", models.BooleanField(default=True)),
                ("broker", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="permissions", to="brokers.broker")),
            ],
            options={"unique_together": {("broker", "permission")}},
        ),
        migrations.AddIndex("brokerconnectionlog", models.Index(fields=["broker_account", "-created_at"], name="brokers_log_acct_created_idx")),
        migrations.AddIndex("brokerconnectionlog", models.Index(fields=["event"], name="brokers_log_event_idx")),
        migrations.RunPython(forwards, backwards),
    ]
