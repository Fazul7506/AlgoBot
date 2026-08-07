class CopyTradingError(Exception): pass
class MirrorExecutionError(CopyTradingError): pass
class VerificationError(CopyTradingError): pass
