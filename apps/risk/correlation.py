class CorrelationService:
    def analyze(self,positions):
        symbols=[getattr(p,'symbol',p.get('symbol')) for p in positions]
        duplicates=[s for s in set(symbols) if symbols.count(s)>1]
        return {'highly_correlated':[],'duplicate_positions':duplicates,'inverse_correlations':[],'concentration_risk':bool(duplicates)}
