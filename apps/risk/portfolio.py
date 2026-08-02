from decimal import Decimal
class PortfolioRiskService:
    def calculate(self,returns=None,exposures=None):
        returns=[Decimal(str(r)) for r in (returns or [])]; exposures=exposures or []
        losses=sorted([r for r in returns if r<0]); var=abs(losses[int(len(losses)*Decimal('0.95'))]) if losses else Decimal('0')
        es=sum(abs(x) for x in losses)/len(losses) if losses else Decimal('0')
        total=sum(Decimal(str(x.get('value',0))) for x in exposures) if exposures else Decimal('0')
        max_exp=max([Decimal(str(x.get('value',0))) for x in exposures], default=Decimal('0'))
        return {'value_at_risk':var,'expected_shortfall':es,'portfolio_exposure':total,'portfolio_drawdown':Decimal('0'),'portfolio_correlation':Decimal('0'),'portfolio_concentration':(max_exp/total if total else Decimal('0'))}
