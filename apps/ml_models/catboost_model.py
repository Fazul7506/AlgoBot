class BaseAlgoBotModel:
    algorithm = 'generic'
    framework = 'sklearn'
    def __init__(self, **params): self.params=params; self.is_trained=False
    def train(self, X, y=None): self.is_trained=True; return {'status':'trained','samples':len(X) if hasattr(X,'__len__') else 0}
    def predict(self, X): return {'direction':'UP','probability':0.55,'confidence':55.0}
    def feature_importance(self): return {}
