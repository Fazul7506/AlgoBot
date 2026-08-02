"""
Self-learning engine for trade analysis, model comparison, and automated retraining.
"""
from typing import Dict, List, Optional

from trading.ai.trade_analysis import TradePatternRecognizer
from trading.ai.model_manager import ModelManager, ModelRecordUpdater
from trading.ai.dataset_builder import build_dataset
from trading.ai.lstm_model import train_lstm
from django.utils import timezone


class ModelRetrainer:
    """Retrains models and manages model registry updates."""

    @staticmethod
    def _create_model_name(symbol: str, timeframe: str, model_type: str) -> str:
        return f"{symbol}_{timeframe}_{model_type}"

    @staticmethod
    def _build_metrics(model, X, y):
        metrics = {
            'n_samples': int(X.shape[0]) if hasattr(X, 'shape') else 0,
        }
        try:
            if hasattr(model, 'score'):
                metrics['accuracy'] = float(model.score(X, y))
        except Exception:
            metrics['accuracy'] = 0.0

        return metrics

    def train_model(
        self,
        model_type: str,
        symbol: str,
        timeframe: str,
        window: int = 200,
        horizon: int = 1,
        seq_length: int = 20,
        epochs: int = 10,
    ) -> Dict[str, object]:
        X, y = build_dataset(symbol, timeframe, window=window, horizon=horizon)
        if X is None or y is None or len(y) < 10:
            return {
                'model_type': model_type,
                'status': 'insufficient_data',
                'symbol': symbol,
                'timeframe': timeframe,
            }

        if model_type == 'lstm':
            trained_model = train_lstm(X, y, seq_length=seq_length, epochs=epochs)
            if trained_model is None:
                return {'model_type': model_type, 'status': 'failed', 'reason': 'lstm_training_failed'}
            storage_path = ModelManager.model_path(symbol, timeframe, model_type)
            trained_model.save(storage_path)
            metrics = {'n_samples': int(X.shape[0]), 'seq_length': seq_length}
            ModelRecordUpdater.upsert_model_record(
                name=self._create_model_name(symbol, timeframe, model_type),
                model_type='lstm',
                storage_path=storage_path,
                metrics=metrics,
            )
            return {'model_type': model_type, 'status': 'trained', 'storage_path': storage_path, 'metrics': metrics}

        try:
            import joblib
            if model_type == 'rf':
                from sklearn.ensemble import RandomForestClassifier
                model = RandomForestClassifier(n_estimators=100, random_state=42)
            elif model_type == 'xgb':
                import xgboost as xgb
                model = xgb.XGBClassifier(n_estimators=100, random_state=42, use_label_encoder=False, eval_metric='logloss')
            elif model_type == 'lgb':
                import lightgbm as lgb
                model = lgb.LGBMClassifier(n_estimators=100, random_state=42)
            else:
                return {'model_type': model_type, 'status': 'unsupported_model_type'}

            model.fit(X, y)
            storage_path = ModelManager.model_path(symbol, timeframe, model_type)
            joblib.dump(model, storage_path)
            metrics = self._build_metrics(model, X, y)

            ModelRecordUpdater.upsert_model_record(
                name=self._create_model_name(symbol, timeframe, model_type),
                model_type=model_type,
                storage_path=storage_path,
                metrics=metrics,
            )

            return {
                'model_type': model_type,
                'status': 'trained',
                'storage_path': storage_path,
                'metrics': metrics,
            }
        except ImportError as e:
            return {'model_type': model_type, 'status': 'skipped', 'reason': str(e)}
        except Exception as e:
            return {'model_type': model_type, 'status': 'failed', 'reason': str(e)}

    def retrain_candidates(
        self,
        symbol: str,
        timeframe: str,
        model_types: Optional[List[str]] = None,
        window: int = 200,
        horizon: int = 1,
        seq_length: int = 20,
        epochs: int = 10,
    ) -> List[Dict[str, object]]:
        types = model_types or ['rf', 'xgb', 'lgb']
        results = []
        for model_type in types:
            results.append(
                self.train_model(
                    model_type=model_type,
                    symbol=symbol,
                    timeframe=timeframe,
                    window=window,
                    horizon=horizon,
                    seq_length=seq_length,
                    epochs=epochs,
                )
            )
        return results


class SelfLearningEngine:
    """Engine that decides when to retrain and summarizes performance."""

    def __init__(self):
        self.pattern_recognizer = TradePatternRecognizer()
        self.model_manager = ModelManager()
        self.retrainer = ModelRetrainer()

    def analyze(self, symbol: str, timeframe: str, strategy_name: Optional[str] = None, days: int = 90) -> Dict[str, object]:
        return {
            'trade_analysis': self.pattern_recognizer.analyze_closed_trades(
                symbol=symbol,
                strategy_name=strategy_name,
                days=days,
            ),
            'model_rankings': self.model_manager.compare_models(symbol, timeframe),
        }

    def should_retrain(
        self,
        analysis: Dict[str, object],
        min_win_rate: float = 0.45,
        max_avg_pnl: float = 0.0,
    ) -> bool:
        trade_analysis = analysis.get('trade_analysis', {})
        return (
            trade_analysis.get('win_rate', 0.0) < min_win_rate or
            trade_analysis.get('avg_pnl', 0.0) <= max_avg_pnl or
            not bool(analysis.get('model_rankings'))
        )

    def review_and_retrain(
        self,
        symbol: str,
        timeframe: str,
        strategy_name: Optional[str] = None,
        days: int = 90,
        window: int = 200,
        horizon: int = 1,
        min_win_rate: float = 0.45,
        max_model_age_days: int = 14,
        model_types: Optional[List[str]] = None,
        force: bool = False,
    ) -> Dict[str, object]:
        analysis = self.analyze(symbol, timeframe, strategy_name=strategy_name, days=days)
        best_model = self.model_manager.best_model(symbol, timeframe)

        needs_retrain = force or self.should_retrain(analysis, min_win_rate=min_win_rate)

        if not needs_retrain and best_model and best_model.get('trained_at'):
            try:
                age_days = (timezone.now() - timezone.datetime.fromisoformat(best_model['trained_at'])).total_seconds() / 86400.0
                if age_days > max_model_age_days:
                    needs_retrain = True
            except Exception:
                needs_retrain = True

        retrain_results = []
        if needs_retrain:
            retrain_results = self.retrainer.retrain_candidates(
                symbol=symbol,
                timeframe=timeframe,
                model_types=model_types,
                window=window,
                horizon=horizon,
            )

        return {
            'analysis': analysis,
            'best_model': best_model,
            'needs_retrain': needs_retrain,
            'retrain_results': retrain_results,
        }
