import numpy as np


def win_rate(wins, losses):

    total = wins + losses

    if total == 0:
        return 0

    return (wins / total) * 100


def expectancy(results):

    if not results:
        return 0

    return np.mean(results)


def sharpe_ratio(results):

    arr = np.array(results)

    if len(arr) < 2:
        return 0

    std = arr.std()

    if std == 0:
        return 0

    return arr.mean() / std


def max_drawdown(results):

    equity = 0
    peak = 0
    max_dd = 0

    for r in results:
        equity += r
        peak = max(peak, equity)
        dd = peak - equity
        max_dd = max(max_dd, dd)

    return max_dd


def sortino_ratio(results, target=0.0):
    """Calculate the Sortino ratio using downside deviation."""
    if not results:
        return 0

    arr = np.array(results)
    downside = arr[arr < target]

    if len(downside) == 0:
        return 0

    downside_std = np.std(downside)
    if downside_std == 0:
        return 0

    return (arr.mean() - target) / downside_std


def profit_factor(results):
    """Return gross profit divided by gross loss for a sequence of trade profits."""
    if not results:
        return 0.0

    gross_profit = sum(r for r in results if r > 0)
    gross_loss = abs(sum(r for r in results if r < 0))
    if gross_loss == 0:
        return float(gross_profit)
    return round(gross_profit / gross_loss, 4)


def roi(starting_balance, ending_balance):
    """Return return on investment as a percentage."""
    if starting_balance == 0:
        return 0.0
    return round(((ending_balance - starting_balance) / starting_balance) * 100, 2)