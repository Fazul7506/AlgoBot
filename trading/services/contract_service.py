from typing import Optional
from django.utils import timezone
from trading.models import Trade
from trading.models.logging import TradeLog, ErrorLog
import logging

logger = logging.getLogger(__name__)


class ContractExecutionService:
    """
    Handles contract buying, selling, and lifecycle management.
    This is the interface between signals/trades and actual Deriv API execution.
    """
    
    def __init__(self, deriv_client=None):
        self.deriv_client = deriv_client
    
    def buy_contract(
        self,
        user,
        symbol: str,
        contract_type: str,
        stake: float,
        trade: Optional[Trade] = None,
        metadata: dict = None
    ) -> Optional[dict]:
        """
        Execute a buy contract order.
        Returns contract details or None if failed.
        """
        try:
            contract_id = f"BUY_{trade.id}" if trade else f"MOCK_{int(timezone.now().timestamp())}"
            
            result = {
                'contract_id': contract_id,
                'symbol': symbol,
                'contract_type': contract_type,
                'stake': stake,
                'entry_price': 0.0,
                'entry_time': timezone.now(),
                'payout': stake * 1.85,
                'status': 'OPEN'
            }
            
            TradeLog.objects.create(
                user=user,
                action='OPEN',
                symbol=symbol,
                contract_type=contract_type,
                stake=stake,
                message=f"Contract opened: {contract_id}",
                metadata=metadata or {}
            )
            
            logger.info(f"Contract buy executed for {user.username}: {contract_id}")
            return result
        except Exception as e:
            logger.error(f"Contract buy failed for {user.username}: {str(e)}", exc_info=True)
            ErrorLog.objects.create(
                user=user,
                error_type="CONTRACT_BUY_FAILED",
                severity="ERROR",
                message=str(e)
            )
            return None
    
    def close_contract(
        self,
        user,
        contract_id: str,
        exit_price: float,
        trade: Optional[Trade] = None,
        metadata: dict = None
    ) -> bool:
        """
        Close/sell a contract.
        Returns True if successful, False otherwise.
        """
        try:
            if trade:
                trade.status = 'CLOSED'
                trade.exit_price = exit_price
                trade.closed_at = timezone.now()
                trade.save()
            
            TradeLog.objects.create(
                user=user,
                action='CLOSE',
                symbol=trade.symbol if trade else 'UNKNOWN',
                contract_type=trade.contract_type if trade else 'UNKNOWN',
                stake=trade.stake if trade else 0,
                message=f"Contract closed: {contract_id} at {exit_price}",
                metadata=metadata or {}
            )
            
            logger.info(f"Contract closed for {user.username}: {contract_id}")
            return True
        except Exception as e:
            logger.error(f"Contract close failed for {user.username}: {str(e)}", exc_info=True)
            return False
