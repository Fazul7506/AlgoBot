from django.db import migrations


LEGACY_BROKER_TABLE = "broker_broker"
LEGACY_ACCOUNT_TABLE = "broker_brokeraccount"
LEGACY_TOKEN_TABLE = "broker_brokentoken"
LEGACY_LOG_TABLE = "broker_brokerconnectionlog"
LEGACY_PERMISSION_TABLE = "broker_brokerpermission"
LEGACY_DERIV_TABLE = "trading_derivaccount"


def _rows(cursor, table):
    cursor.execute(f'SELECT * FROM "{table}"')
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _canonical_status(value):
    value = str(value or "active").lower()
    return value if value in {"active", "disabled", "maintenance", "degraded", "offline", "coming_soon"} else "active"


def forwards(apps, schema_editor):
    Broker = apps.get_model("brokers", "Broker")
    BrokerAccount = apps.get_model("brokers", "BrokerAccount")
    BrokerConnectionLog = apps.get_model("brokers", "BrokerConnectionLog")
    BrokerPermission = apps.get_model("brokers", "BrokerPermission")
    db = schema_editor.connection
    tables = set(db.introspection.table_names())

    # This migration is deliberately data-preserving. If a canonical account is
    # already owned by a different user, abort instead of silently reassigning or
    # overwriting credentials. The transaction keeps the production database intact.
    broker_map = {}
    if LEGACY_BROKER_TABLE in tables:
        with db.cursor() as cursor:
            for row in _rows(cursor, LEGACY_BROKER_TABLE):
                slug = str(row.get("slug") or row.get("name") or "legacy").lower().replace(" ", "_")
                broker_type = slug[:40]
                broker = Broker.objects.filter(broker_type=broker_type).first()
                if broker is None:
                    broker = Broker.objects.filter(name=row.get("name") or slug).first()
                if broker is None:
                    broker = Broker.objects.create(
                        name=row.get("name") or slug.title(),
                        broker_type=broker_type,
                        status=_canonical_status(row.get("status")),
                        metadata={"migrated_from": "apps.broker", "legacy_id": row.get("id")},
                    )
                else:
                    metadata = dict(broker.metadata or {})
                    metadata.setdefault("migrated_from", "apps.broker")
                    metadata.setdefault("legacy_ids", []).append(row.get("id"))
                    broker.metadata = metadata
                    broker.save(update_fields=["metadata"])
                broker_map[row.get("id")] = broker

    if LEGACY_ACCOUNT_TABLE in tables:
        with db.cursor() as cursor:
            account_rows = _rows(cursor, LEGACY_ACCOUNT_TABLE)
            token_rows = {}
            if LEGACY_TOKEN_TABLE in tables:
                for token in _rows(cursor, LEGACY_TOKEN_TABLE):
                    token_rows[token.get("broker_account_id")] = token

            for row in account_rows:
                broker = broker_map.get(row.get("broker_id"))
                if broker is None:
                    continue
                account_id = str(row.get("broker_account_id") or "")
                if not account_id:
                    continue
                account = BrokerAccount.objects.filter(broker=broker, account_id=account_id).first()
                if account is not None and account.user_id != row.get("user_id"):
                    raise RuntimeError(
                        f"Canonical broker account conflict for {broker.broker_type}:{account_id}; "
                        "the legacy record belongs to a different user. Migration stopped without deleting legacy data."
                    )
                if account is None:
                    account = BrokerAccount(
                        broker=broker,
                        account_id=account_id,
                        user_id=row.get("user_id"),
                    )
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
                    # Legacy tokens are already encrypted with the same service;
                    # ciphertext is copied without ever materializing plaintext.
                    account.access_token = token.get("access_token") or account.access_token
                    account.refresh_token = token.get("refresh_token") or account.refresh_token
                    account.expires_at = token.get("expires_at")
                    account.last_refresh = token.get("last_refresh")
                    account.token_status = token.get("status") or "active"
                account.save()

    # The newer trading.DerivAccount stored the same encrypted OAuth credentials.
    # Prefer it when it contains a credential that the canonical account does not.
    if LEGACY_DERIV_TABLE in tables:
        with db.cursor() as cursor:
            for row in _rows(cursor, LEGACY_DERIV_TABLE):
                account_id = str(row.get("account_id") or "")
                if not account_id:
                    continue
                broker = Broker.objects.filter(broker_type="deriv").first()
                if broker is None:
                    broker = Broker.objects.create(name="Deriv", broker_type="deriv", status="active", supports_live=True)
                account = BrokerAccount.objects.filter(broker=broker, account_id=account_id).first()
                if account is not None and account.user_id != row.get("user_id"):
                    raise RuntimeError(
                        f"Canonical Deriv account conflict for {account_id}; migration stopped without deleting legacy data."
                    )
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
                if broker is None or not row.get("permission"):
                    continue
                BrokerPermission.objects.update_or_create(
                    broker=broker,
                    permission=row["permission"],
                    defaults={"enabled": bool(row.get("enabled", True))},
                )

    if LEGACY_LOG_TABLE in tables:
        with db.cursor() as cursor:
            for row in _rows(cursor, LEGACY_LOG_TABLE):
                broker = broker_map.get(row.get("broker_id"))
                if broker is None:
                    continue
                account_id = str(row.get("broker_account_id") or "")
                account = BrokerAccount.objects.filter(broker=broker, account_id=account_id).first()
                if account is None:
                    continue
                BrokerConnectionLog.objects.get_or_create(
                    broker_account=account,
                    status=row.get("status") or "unknown",
                    latency=row.get("latency"),
                    event=row.get("event") or "legacy",
                    created_at=row.get("created_at"),
                )


def backwards(apps, schema_editor):
    raise RuntimeError("Canonical broker migration is intentionally irreversible; restore from the production backup to roll back.")


class Migration(migrations.Migration):
    dependencies = [("brokers", "0001_initial")]
    operations = [
        migrations.AddField(
            model_name="brokeraccount",
            name="access_token",
            field=__import__("django.db.models").db.models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="brokeraccount",
            name="refresh_token",
            field=__import__("django.db.models").db.models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="brokeraccount",
            name="token_status",
            field=__import__("django.db.models").db.models.CharField(default="active", db_index=True, max_length=20),
        ),
        migrations.AddField(
            model_name="brokeraccount",
            name="expires_at",
            field=__import__("django.db.models").db.models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="brokeraccount",
            name="last_refresh",
            field=__import__("django.db.models").db.models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name="brokeraccount",
            index=__import__("django.db.models").db.models.Index(fields=["user", "token_status"], name="brokers_ba_user_tok_idx"),
        ),
        migrations.CreateModel(
            name="BrokerConnectionLog",
            fields=[
                ("id", __import__("django.db.models").db.models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", __import__("django.db.models").db.models.CharField(max_length=50)),
                ("latency", __import__("django.db.models").db.models.FloatField(blank=True, null=True)),
                ("event", __import__("django.db.models").db.models.CharField(max_length=120)),
                ("created_at", __import__("django.db.models").db.models.DateTimeField(auto_now_add=True)),
                ("broker_account", __import__("django.db.models").db.models.ForeignKey(on_delete=__import__("django.db.models").db.models.deletion.CASCADE, related_name="connection_logs", to="brokers.brokeraccount")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="BrokerPermission",
            fields=[
                ("id", __import__("django.db.models").db.models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("permission", __import__("django.db.models").db.models.CharField(max_length=80)),
                ("enabled", __import__("django.db.models").db.models.BooleanField(default=True)),
                ("broker", __import__("django.db.models").db.models.ForeignKey(on_delete=__import__("django.db.models").db.models.deletion.CASCADE, related_name="permissions", to="brokers.broker")),
            ],
            options={"unique_together": {("broker", "permission")}},
        ),
        migrations.AddIndex(
            model_name="brokerconnectionlog",
            index=__import__("django.db.models").db.models.Index(fields=["broker_account", "-created_at"], name="brokers_log_acct_created_idx"),
        ),
        migrations.AddIndex(
            model_name="brokerconnectionlog",
            index=__import__("django.db.models").db.models.Index(fields=["event"], name="brokers_log_event_idx"),
        ),
        migrations.RunPython(forwards, backwards),
    ]
