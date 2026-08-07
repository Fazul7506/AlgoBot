from .paper import PaperTradingAdapter
class Adapter(PaperTradingAdapter):
    broker_type = __name__.rsplit('.', 1)[-1]
