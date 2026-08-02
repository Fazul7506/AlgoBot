class AIEngineError(Exception): pass
class ModelNotActiveError(AIEngineError): pass
class InvalidTrainingDataError(AIEngineError): pass
class InferenceError(AIEngineError): pass
