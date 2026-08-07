class PortfolioError(Exception):
    """Base portfolio engine exception."""


class AllocationError(PortfolioError):
    """Raised when portfolio allocation is invalid."""


class RebalancingError(PortfolioError):
    """Raised when rebalancing cannot be completed."""
