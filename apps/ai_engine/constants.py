MODEL_STATUS = ("experimental", "active", "champion", "challenger", "archived", "failed")
ALGORITHMS = ("random_forest", "xgboost", "lightgbm", "catboost", "extra_trees", "svm", "logistic_regression", "lstm", "gru", "cnn", "transformer", "ensemble")
RECOMMENDATIONS = ("BUY", "SELL", "WAIT", "EXIT", "REDUCE RISK", "INCREASE POSITION", "DO NOT TRADE")
REGIMES = ("trending", "strong_trend", "sideways", "volatile", "low_volatility", "accumulation", "distribution", "breakout", "reversal")
WEBSOCKET_EVENTS = ("PredictionUpdated", "RecommendationUpdated", "TrainingStarted", "TrainingCompleted", "ModelActivated", "ModelFailed", "RegimeChanged", "AnomalyDetected")
CONFIDENCE_LABELS = [(0, "Very Low"), (25, "Low"), (50, "Medium"), (75, "High"), (90, "Very High")]
