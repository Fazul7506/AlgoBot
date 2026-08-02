from apps.smart_money.services import SmartMoneyEngine, FairValueGapService, InstitutionalBiasService, ConfluenceEngine
CANDLES=[{'open':1,'high':2,'low':.8,'close':1.5,'volume':10},{'open':1.5,'high':2.1,'low':1.2,'close':1.8,'volume':12},{'open':1.8,'high':2.4,'low':1.7,'close':2.3,'volume':20},{'open':2.3,'high':2.8,'low':2.2,'close':2.7,'volume':22},{'open':2.7,'high':3.2,'low':2.6,'close':3.1,'volume':30}]
def test_engine_returns_core_sections():
    result=SmartMoneyEngine().analyze('R_100','M1',CANDLES)
    assert result['symbol']=='R_100'; assert 'market_structure' in result; assert 'confluence' in result

def test_bias_and_confluence_are_bounded():
    assert 0 <= InstitutionalBiasService().calculate(CANDLES)['confidence'] <= 100
    assert 0 <= ConfluenceEngine().score(CANDLES)['score'] <= 100

def test_fvg_detection_is_deterministic():
    assert FairValueGapService().detect(CANDLES)==FairValueGapService().detect(CANDLES)
