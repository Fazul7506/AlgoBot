from django.utils import timezone
class StrategyLifecycleService:
    allowed={'created':['validated','archived'],'validated':['loaded','archived'],'loaded':['initialized','stopped'],'initialized':['running','paused','stopped'],'running':['paused','stopped'],'paused':['running','stopped'],'stopped':['archived','loaded'],'archived':[]}
    def transition(self, strategy, state):
        if state not in self.allowed.get(strategy.lifecycle_state,[]): raise ValueError(f'Cannot move {strategy.lifecycle_state} to {state}')
        strategy.lifecycle_state=state; strategy.updated_at=timezone.now(); strategy.save(update_fields=['lifecycle_state','updated_at']); return strategy
