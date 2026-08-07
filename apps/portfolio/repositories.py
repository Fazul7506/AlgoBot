from .models import Portfolio


class PortfolioRepository:
    def for_user(self, user):
        return Portfolio.objects.filter(user=user).prefetch_related("accounts", "allocations")

    def active(self):
        return Portfolio.objects.filter(status="active")
