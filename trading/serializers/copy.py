from rest_framework import serializers
from django.contrib.auth.models import User
from core.serializers import UserSerializer
from trading.models.copy import CopyFollow, LeaderStats, CopyTrade


class CopyFollowSerializer(serializers.ModelSerializer):
    leader_username = serializers.CharField(source='leader.username', read_only=True)
    follower_username = serializers.CharField(source='follower.username', read_only=True)

    class Meta:
        model = CopyFollow
        fields = [
            'id', 'leader', 'leader_username', 'follower', 'follower_username',
            'allocation_type', 'allocation_value', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'leader_username', 'follower_username', 'created_at', 'updated_at']


class LeaderStatsSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = LeaderStats
        fields = [
            'id', 'user', 'followers_count', 'assets_under_management',
            'total_trades', 'win_rate', 'avg_return_pct', 'last_updated'
        ]
        read_only_fields = ['id', 'user', 'last_updated']


class CopyTradeSerializer(serializers.ModelSerializer):
    follower_username = serializers.CharField(source='follower.username', read_only=True)

    class Meta:
        model = CopyTrade
        fields = [
            'id', 'leader_trade_id', 'follower', 'follower_username',
            'follower_trade', 'amount', 'status', 'created_at', 'executed_at'
        ]
        read_only_fields = ['id', 'follower_username', 'created_at', 'executed_at']
