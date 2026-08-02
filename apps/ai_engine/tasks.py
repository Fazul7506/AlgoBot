from deriv_platform.celery import app
from .services import TrainingService, PredictionService, HyperparameterOptimizationService, EnsembleService, AnomalyDetectionService, FeatureEngineeringService
@app.task
def train_model(model_id=None): return TrainingService().train(mode='scheduled').id
@app.task
def generate_features(symbol, timeframe='M1', context=None): return FeatureEngineeringService().build_features(symbol,timeframe,context or {})
@app.task
def refresh_prediction(symbol, timeframe='M1', context=None): return PredictionService().predict(symbol,timeframe,context or {}).id
@app.task
def optimize_hyperparameters(algorithm, search='random_search'): return HyperparameterOptimizationService().optimize(algorithm, search)
@app.task
def recalculate_ensemble(predictions): return EnsembleService().combine(predictions)
@app.task
def scan_anomalies(symbol, features):
    obj=AnomalyDetectionService().scan(symbol,features); return obj.id if obj else None
@app.task
def evaluate_model(model_id): return {'model_id':model_id,'status':'evaluated'}
@app.task
def compare_champion_challenger(): return {'status':'compared'}
