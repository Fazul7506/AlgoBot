from django.test import TestCase
from apps.ai_engine.services import AIEngine, FeatureEngineeringService, TrainingService, EnsembleService, ExplainabilityService, HyperparameterOptimizationService
from apps.ai_engine.models import AIModel
class AIEngineServiceTests(TestCase):
    def context(self): return {'market_data':{'open':1,'high':2,'low':.5,'close':1.7,'volatility':1.2}, 'indicators':{'rsi':55}, 'smart_money':{'bos':True,'confluence_score':70}, 'risk':{'portfolio_risk':.1}, 'strategy':{'confidence':80,'win_rate':60}}
    def test_end_to_end_prediction_recommendation_regime(self):
        result=AIEngine().analyze('R_100','M1',self.context())
        self.assertIn(result['prediction'].prediction, ['UP','DOWN']); self.assertTrue(result['recommendation'].recommendation); self.assertTrue(result['regime'].regime)
    def test_feature_engineering_sources(self): self.assertIn('confluence_score', FeatureEngineeringService().build_features('R_100','M1',self.context()))
    def test_training_registry_and_optimization(self):
        m=AIModel.objects.create(name='rf',version='1',algorithm='random_forest',status='champion')
        self.assertEqual(TrainingService().train(m).status,'completed'); self.assertIn('best_params', HyperparameterOptimizationService().optimize('random_forest'))
    def test_ensemble_and_explainability(self):
        self.assertEqual(EnsembleService().combine([{'probability':.7},{'probability':.8}])['direction'],'UP')
        self.assertIn('feature_importance', ExplainabilityService().explain({'rsi':55,'risk':.2}))
