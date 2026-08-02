from .models import Position
class PositionManager:
    def open_positions(self): return Position.objects.filter(status='open')
