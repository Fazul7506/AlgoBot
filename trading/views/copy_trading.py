import logging
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Count, Sum, Avg, F

from trading.models.copy import CopyFollow, LeaderStats, CopyTrade
from trading.models import Trade
from trading.serializers.copy import CopyFollowSerializer, LeaderStatsSerializer, CopyTradeSerializer
from trading.services.copy_service import CopyService

logger = logging.getLogger(__name__)


class CopyTradingViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['get'])
    def leaderboard(self, request):
        """Return leader rankings and performance metrics."""
        try:
            leaders = LeaderStats.objects.all().order_by('-assets_under_management')[:50]
            serializer = LeaderStatsSerializer(leaders, many=True)
            return Response({'status': 'success', 'data': serializer.data}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception('Failed to load leaderboard')
            return Response({'status': 'error', 'message': 'Could not load leaderboard'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'])
    def my_following(self, request):
        try:
            follows = CopyFollow.objects.filter(follower=request.user, is_active=True)
            serializer = CopyFollowSerializer(follows, many=True)
            return Response({'status': 'success', 'data': serializer.data}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception('Failed to load following list')
            return Response({'status': 'error', 'message': 'Could not load following list'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'])
    def my_followers(self, request):
        try:
            follows = CopyFollow.objects.filter(leader=request.user, is_active=True)
            serializer = CopyFollowSerializer(follows, many=True)
            return Response({'status': 'success', 'data': serializer.data}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception('Failed to load followers list')
            return Response({'status': 'error', 'message': 'Could not load followers list'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'])
    def follow(self, request):
        leader_id = request.data.get('leader_id')
        allocation_type = request.data.get('allocation_type', 'PERCENT')
        allocation_value = float(request.data.get('allocation_value', 10.0))

        if not leader_id:
            return Response({'status': 'error', 'message': 'leader_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            leader = User.objects.filter(id=leader_id).first()
            if not leader:
                return Response({'status': 'error', 'message': 'Leader not found'}, status=status.HTTP_404_NOT_FOUND)

            follow = CopyService().follow(leader, request.user, allocation_type=allocation_type, allocation_value=allocation_value)
            serializer = CopyFollowSerializer(follow)
            return Response({'status': 'success', 'data': serializer.data}, status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.exception('Failed to follow leader')
            return Response({'status': 'error', 'message': 'Could not follow leader'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'])
    def unfollow(self, request):
        leader_id = request.data.get('leader_id')
        if not leader_id:
            return Response({'status': 'error', 'message': 'leader_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            leader = User.objects.filter(id=leader_id).first()
            if not leader:
                return Response({'status': 'error', 'message': 'Leader not found'}, status=status.HTTP_404_NOT_FOUND)

            CopyService().unfollow(leader, request.user)
            return Response({'status': 'success', 'message': 'Unfollowed leader'}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception('Failed to unfollow leader')
            return Response({'status': 'error', 'message': 'Could not unfollow leader'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'])
    def copied_trades(self, request):
        try:
            trades = CopyTrade.objects.filter(follower=request.user).order_by('-created_at')[:100]
            serializer = CopyTradeSerializer(trades, many=True)
            return Response({'status': 'success', 'data': serializer.data}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception('Failed to load copied trades')
            return Response({'status': 'error', 'message': 'Could not load copied trades'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'])
    def leader_performance(self, request):
        leader_id = request.query_params.get('leader_id')
        if not leader_id:
            return Response({'status': 'error', 'message': 'leader_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            leader = User.objects.filter(id=leader_id).first()
            if not leader:
                return Response({'status': 'error', 'message': 'Leader not found'}, status=status.HTTP_404_NOT_FOUND)

            stats = LeaderStats.objects.filter(user=leader).first()
            if not stats:
                return Response({'status': 'error', 'message': 'Leader stats not available'}, status=status.HTTP_404_NOT_FOUND)

            serializer = LeaderStatsSerializer(stats)
            return Response({'status': 'success', 'data': serializer.data}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception('Failed to load leader performance')
            return Response({'status': 'error', 'message': 'Could not load leader performance'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
