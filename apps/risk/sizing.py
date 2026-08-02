from decimal import Decimal
class PositionSizingService:
    def calculate(self,balance,risk_per_trade=None,stop_loss_distance=None,method='percentage_risk',fixed_stake=None,win_rate=None,reward_risk=None,atr=None,volatility=None):
        balance=Decimal(str(balance or 0)); risk=Decimal(str(risk_per_trade or '0.02'))
        if method=='fixed_stake': return max(Decimal('0'),Decimal(str(fixed_stake or 0)))
        if method=='fixed_fractional': return balance*risk
        if method=='kelly':
            p=Decimal(str(win_rate or '0.5')); b=Decimal(str(reward_risk or '1')); f=max(Decimal('0'), min((p*b-(1-p))/b, Decimal('0.25'))); return balance*f
        if method=='atr_based':
            distance=Decimal(str(atr or stop_loss_distance or 1)); return (balance*risk)/max(distance,Decimal('0.00000001'))
        if method=='volatility_adjusted':
            vol=max(Decimal(str(volatility or '1')),Decimal('0.00000001')); return (balance*risk)/vol
        if method=='dynamic': return balance*min(risk*Decimal('1.25'),Decimal('0.05'))
        return (balance*risk)/max(Decimal(str(stop_loss_distance or 1)),Decimal('0.00000001'))
