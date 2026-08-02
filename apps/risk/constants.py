from decimal import Decimal
RISK_LEVELS=('very_conservative','conservative','moderate','aggressive','very_aggressive','custom')
SIZING_METHODS=('fixed_stake','fixed_fractional','kelly','percentage_risk','atr_based','volatility_adjusted','dynamic','ai_adaptive')
RULE_TYPES=('max_risk_per_trade','max_daily_loss','max_daily_profit','max_weekly_loss','max_monthly_loss','max_drawdown','max_consecutive_losses','max_consecutive_wins','max_open_positions','max_simultaneous_strategies','max_symbol_exposure','max_market_exposure','max_broker_exposure','minimum_balance','max_stake_limit')
RISK_SCORE_LOW=30; RISK_SCORE_MEDIUM=60; RISK_SCORE_HIGH=80
DEFAULT_PROFILE_LIMITS={'very_conservative':(Decimal('0.005'),Decimal('0.01'),Decimal('0.02'),Decimal('0.03'),3,Decimal('0.10')),'conservative':(Decimal('0.01'),Decimal('0.02'),Decimal('0.03'),Decimal('0.05'),5,Decimal('0.20')),'moderate':(Decimal('0.02'),Decimal('0.04'),Decimal('0.06'),Decimal('0.10'),10,Decimal('0.35')),'aggressive':(Decimal('0.03'),Decimal('0.06'),Decimal('0.10'),Decimal('0.15'),15,Decimal('0.50')),'very_aggressive':(Decimal('0.05'),Decimal('0.10'),Decimal('0.15'),Decimal('0.25'),25,Decimal('0.75'))}
