from .models import Order, ExecutionQueue
class OrderManager:
    def for_user(self,user): return Order.objects.filter(user=user)
class ExecutionQueueManager:
    def ready(self): return ExecutionQueue.objects.filter(status__in=['pending','retry']).order_by('priority','created_at')
