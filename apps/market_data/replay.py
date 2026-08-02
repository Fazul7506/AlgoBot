from .constants import EVENT_REPLAY_STARTED, EVENT_REPLAY_STOPPED
from .models import Tick
from .websocket import event_bus

class ReplayService:
    def __init__(self): self.state = "stopped"; self.speed = 1.0; self.position = None
    def play(self, symbol, start_epoch=None, end_epoch=None, speed=1.0):
        self.state="playing"; self.speed=speed; event_bus.publish(EVENT_REPLAY_STARTED,{"symbol":symbol,"speed":speed})
        qs=Tick.objects.filter(symbol__symbol=symbol).order_by("epoch")
        if start_epoch: qs=qs.filter(epoch__gte=start_epoch)
        if end_epoch: qs=qs.filter(epoch__lte=end_epoch)
        return qs
    def pause(self): self.state="paused"
    def stop(self): self.state="stopped"; event_bus.publish(EVENT_REPLAY_STOPPED,{})
    def fast_forward(self, factor=2): self.speed *= factor
    def slow_motion(self, factor=2): self.speed /= factor
    def jump_to_time(self, epoch): self.position=epoch
