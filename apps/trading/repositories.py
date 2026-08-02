from .models import Position
class PositionRepository:
    def open_for_order(self, order, entry_price): return Position.objects.create(order=order,symbol=order.symbol,entry_price=entry_price,current_price=entry_price,status='open')
    def open(self): return Position.objects.filter(status='open')
    def closed(self): return Position.objects.filter(status='closed')
