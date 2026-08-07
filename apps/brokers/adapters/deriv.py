from .paper import PaperTradingAdapter
class DerivAdapter(PaperTradingAdapter):
    broker_type='deriv'
    async def place_order(self, order):
        result=await super().place_order(order); result['broker_order_id']=result['broker_order_id'].replace('PAPER','DERIV'); result['contract_type']=order.contract_type; return result
