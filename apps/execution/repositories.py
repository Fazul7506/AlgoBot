from .models import Order, ExecutionLog, ExecutionQueue
class OrderRepository:
    def create(self, **data): return Order.objects.create(**data)
    def get_for_user(self, user, pk): return Order.objects.get(pk=pk,user=user)
class ExecutionLogRepository:
    def log(self, order, event, status, message='', latency=None, broker_response=None): return ExecutionLog.objects.create(order=order,event=event,status=status,message=message,latency=latency,broker_response=broker_response or {})
class ExecutionQueueRepository:
    def enqueue(self, order, priority=5, queue_type='priority'): return ExecutionQueue.objects.update_or_create(order=order,defaults={'priority':priority,'queue_type':queue_type,'status':'pending'})[0]
