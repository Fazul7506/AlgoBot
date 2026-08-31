from rest_framework import serializers
from .models import Broker, BrokerAccount, BrokerConnection, Order, ExecutionReport, Position, TradeReconciliation


class BrokerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Broker
        fields = '__all__'


class BrokerAccountSerializer(serializers.ModelSerializer):
    broker = serializers.SerializerMethodField()
    broker_name = serializers.CharField(source='broker.name', read_only=True)
    broker_account_id = serializers.CharField(source='account_id', read_only=True)
    account_type = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()
    branding = serializers.SerializerMethodField()
    is_default = serializers.BooleanField(source='is_preferred', read_only=True)
    is_connected = serializers.SerializerMethodField()
    credential_status = serializers.CharField(read_only=True)
    data_freshness = serializers.SerializerMethodField()
    switch_enabled = serializers.SerializerMethodField()
    equity = serializers.SerializerMethodField()
    margin = serializers.SerializerMethodField()
    free_margin = serializers.SerializerMethodField()
    net_profit_loss = serializers.SerializerMethodField()

    class Meta:
        model = BrokerAccount
        fields = ['id','user','broker','broker_name','broker_account_id','account_id','account_type','avatar_url','display_name','branding','currency','balance','equity','margin','free_margin','net_profit_loss','status','is_preferred','is_default','is_connected','credential_status','last_synced_at','data_freshness','switch_enabled','created_at']
        read_only_fields = ['user','balance','equity','margin','free_margin','net_profit_loss','last_synced_at','broker_account_id','account_type','avatar_url','display_name','branding','is_default','is_connected','data_freshness','switch_enabled']

    def _is_deriv(self, obj):
        return str(obj.broker.broker_type or '').lower() == 'deriv'

    def _realtime(self, obj):
        value = (obj.credentials or {}).get('realtime') or {}
        return value if isinstance(value, dict) else {}

    def _broker_metadata(self, obj):
        value = obj.broker.metadata or {}
        return value if isinstance(value, dict) else {}

    def get_broker(self, obj):
        metadata = self._broker_metadata(obj)
        return {'id':obj.broker_id,'name':obj.broker.name,'type':obj.broker.broker_type,'status':obj.broker.status,'avatar_url':str(metadata.get('avatar_url') or '')}

    def get_account_type(self, obj):
        value = str((obj.credentials or {}).get('account_type') or '').lower()
        return value if value in {'real','demo'} else 'unknown'

    def get_avatar_url(self, obj):
        realtime, metadata = self._realtime(obj), self._broker_metadata(obj)
        return str(realtime.get('avatar_url') or metadata.get('avatar_url') or '')

    def get_display_name(self, obj):
        return f'{obj.broker.name} · {obj.account_id}'

    def get_branding(self, obj):
        realtime, metadata = self._realtime(obj), self._broker_metadata(obj)
        account_type = self.get_account_type(obj)
        provider = str(metadata.get('provider') or obj.broker.name)
        avatar_url = str(realtime.get('avatar_url') or metadata.get('avatar_url') or '')
        return {'provider':provider,'powered_by':provider,'country_code':str(realtime.get('country_code') or metadata.get('country_code') or '').upper(),'country_name':str(realtime.get('country_name') or metadata.get('country_name') or ''),'flag':str(realtime.get('flag') or metadata.get('flag') or ''),'avatar_url':avatar_url,'account_type':account_type,'label':f'{provider} Demo Account' if account_type == 'demo' else f'{provider} Real Account' if account_type == 'real' else f'{provider} Account'}

    def get_is_connected(self, obj):
        return obj.connections.filter(status='connected').exists()

    def get_data_freshness(self, obj):
        if not obj.last_synced_at: return {'state':'never_synced','seconds':None}
        from django.utils import timezone
        seconds=max(0,int((timezone.now()-obj.last_synced_at).total_seconds()))
        return {'state':'fresh' if seconds <= 60 else 'stale','seconds':seconds}

    def get_switch_enabled(self, obj):
        # Account selection is an authenticated control-plane operation. Trading
        # safety is enforced separately by the server during execution.
        return True

    def get_equity(self, obj):
        realtime=self._realtime(obj)
        if realtime.get('equity') is not None: return realtime['equity']
        if not self._is_deriv(obj) or obj.equity != 0: return obj.equity
        return None

    def get_margin(self, obj):
        realtime=self._realtime(obj)
        if realtime.get('margin') is not None: return realtime['margin']
        if not self._is_deriv(obj) or obj.margin != 0: return obj.margin
        return None

    def get_free_margin(self, obj):
        realtime=self._realtime(obj)
        if realtime.get('available_margin') is not None: return realtime['available_margin']
        if not self._is_deriv(obj) or obj.free_margin != 0: return obj.free_margin
        return None

    def get_net_profit_loss(self, obj):
        return self._realtime(obj).get('unrealized_pnl')


class BrokerConnectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = BrokerConnection
        fields = '__all__'


class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = '__all__'
        read_only_fields = ['user','broker','status','submitted_at','executed_at','broker_order_id']

    def validate(self, attrs):
        attrs=super().validate(attrs); account=attrs.get('account'); request=self.context.get('request'); user=getattr(request,'user',None)
        if account is None: return attrs
        if not user or not user.is_authenticated or account.user_id != user.id: raise serializers.ValidationError({'account':'The selected broker account does not belong to the authenticated user.'})
        if not account.is_preferred: raise serializers.ValidationError({'account':'The selected broker account is stale. Select the current active broker account before submitting an order.'})
        if account.status != 'active' or account.broker.status != 'active': raise serializers.ValidationError({'account':'The current broker account is not active.'})
        return attrs


class ExecutionReportSerializer(serializers.ModelSerializer):
    symbol=serializers.CharField(source='order.symbol',read_only=True); direction=serializers.CharField(source='order.direction',read_only=True); broker_order_id=serializers.CharField(source='order.broker_order_id',read_only=True)
    class Meta:
        model=ExecutionReport
        fields=['id','order','execution_price','requested_price','slippage','latency','fees','status','raw_report','created_at','symbol','direction','broker_order_id']


class PositionSerializer(serializers.ModelSerializer):
    class Meta: model=Position; fields='__all__'


class TradeReconciliationSerializer(serializers.ModelSerializer):
    class Meta: model=TradeReconciliation; fields='__all__'
