"""Production ensemble inference for broker-independent trading models."""
from __future__ import annotations
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
import numpy as np

MODEL_DIR=os.environ.get("AI_MODEL_DIR",os.path.join(os.path.dirname(__file__),"models"))
DEFAULT_WEIGHTS={"rf":1.0,"xgb":1.0,"lgb":1.0,"lstm":1.0}

def _clip_probability(value:Any)->float:
    try: return float(np.clip(float(value),0.0,1.0))
    except (TypeError,ValueError): return .5

class EnsemblePredictor:
    """Run only models compatible with the current feature contract.

    The current contract is the ordered candlestick/price-action feature vector.
    Old artifacts with a different feature count are ignored until retraining.
    """
    def __init__(self,symbol:str,timeframe:str,weights:dict[str,float]|None=None):
        self.symbol=symbol; self.timeframe=timeframe; self.models={}; self.weights=dict(DEFAULT_WEIGHTS)
        if weights: self.weights.update({k:max(0.0,float(v)) for k,v in weights.items()})
        self._load_models()
    def _load_models(self)->None:
        try: import joblib
        except Exception: joblib=None
        if joblib:
            for model_type in ("rf","xgb","lgb"):
                path=os.path.join(MODEL_DIR,f"{self.symbol}_{self.timeframe}_{model_type}.pkl")
                if os.path.exists(path):
                    try: self.models[model_type]=joblib.load(path)
                    except Exception: pass
        try:
            from tensorflow import keras
            path=os.path.join(MODEL_DIR,f"{self.symbol}_{self.timeframe}_lstm.keras")
            if os.path.exists(path): self.models["lstm"]=keras.models.load_model(path)
        except Exception: pass
    @staticmethod
    def _predict_one(model_type:str,model:Any,X:np.ndarray)->float:
        if model_type=="lstm":
            raw=model.predict(X.reshape(X.shape[0],-1,1),verbose=0); return _clip_probability(np.asarray(raw).reshape(-1)[-1])
        if hasattr(model,"predict_proba"):
            raw=model.predict_proba(X); classes=list(getattr(model,"classes_",[0,1])); return _clip_probability(raw[-1,classes.index(1)] if 1 in classes else raw[-1,-1])
        return _clip_probability(np.asarray(model.predict(X)).reshape(-1)[-1])
    @staticmethod
    def _validate_input(model:Any,X:np.ndarray)->None:
        expected=getattr(model,"n_features_in_",None)
        if expected is not None and int(expected)!=int(X.shape[1]): raise ValueError(f"incompatible model feature count: model={expected}, current={X.shape[1]}")
    def _run_models(self,X:np.ndarray)->list[dict[str,Any]]:
        def run(name,model):
            self._validate_input(model,X)
            return {"model":name,"probability":self._predict_one(name,model,X),"weight":self.weights.get(name,1.0)}
        results=[]; concurrent=os.environ.get("AI_ENSEMBLE_CONCURRENCY","0")=="1"
        if concurrent and len(self.models)>1:
            with ThreadPoolExecutor(max_workers=min(4,len(self.models))) as pool:
                futures={pool.submit(run,n,m):n for n,m in self.models.items()}
                for f in as_completed(futures):
                    try: results.append(f.result())
                    except Exception: pass
        else:
            for name,model in self.models.items():
                try: results.append(run(name,model))
                except Exception: pass
        return results
    @staticmethod
    def consensus(predictions:list[dict[str,Any]],avoid_band=.10,min_confidence=.65)->dict[str,Any]:
        if not predictions: return {"decision":"AVOID","direction":"NO_MODELS","probability":.5,"confidence":0.0,"agreement":0.0,"models_used":0,"model_types":[],"model_outputs":[]}
        usable=[p for p in predictions if float(p.get("weight",0))>0] or predictions; weights=np.asarray([max(0.,float(p.get("weight",1))) for p in usable],dtype=float); probs=np.asarray([_clip_probability(p.get("probability",.5)) for p in usable],dtype=float)
        if weights.sum()<=0: weights=np.ones_like(probs)
        probability=float(np.average(probs,weights=weights)); std=float(np.sqrt(np.average((probs-probability)**2,weights=weights))); agreement=max(0.,min(1.,1.-std/.5)); strength=abs(probability-.5)*2.; confidence=max(0.,min(1.,strength*(.5+.5*agreement))); direction="UP" if probability>.5 else "DOWN" if probability<.5 else "FLAT"; decision="BUY" if probability>.5 else "SELL" if probability<.5 else "AVOID"
        if abs(probability-.5)<avoid_band or confidence<min_confidence: decision="AVOID"
        return {"decision":decision,"direction":direction,"probability":round(probability,4),"confidence":round(confidence,4),"agreement":round(agreement,4),"std_dev":round(std,4),"models_used":len(usable),"model_types":[p["model"] for p in usable],"model_outputs":usable}
    def predict(self,X:np.ndarray)->dict[str,Any]:
        return self.consensus(self._run_models(np.asarray(X,dtype=float)),avoid_band=float(os.environ.get("AI_ENSEMBLE_AVOID_BAND","0.10")),min_confidence=float(os.environ.get("AI_ENSEMBLE_MIN_CONFIDENCE","0.65")))
