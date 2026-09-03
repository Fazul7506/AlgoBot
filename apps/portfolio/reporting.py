"""Portfolio reporting service.

Reports are derived from the supplied portfolio and its persisted related data.
No synthetic performance values are generated.
"""

import csv
import io


class ReportingService:
    def generate(self, portfolio, report_type="executive", export_format="json"):
        nav = float(getattr(portfolio, "net_asset_value", 0) or 0)
        equity = float(getattr(portfolio, "equity", nav) or nav)
        balance = float(getattr(portfolio, "current_balance", 0) or 0)
        initial_balance = float(getattr(portfolio, "initial_balance", 0) or 0)
        total_return = ((nav - initial_balance) / initial_balance) if initial_balance else 0.0

        allocations = getattr(portfolio, "allocations", None)
        performance_relation = getattr(portfolio, "performance", None)
        latest_performance = None
        if performance_relation is not None and hasattr(performance_relation, "order_by"):
            latest_performance = performance_relation.order_by("-created_at").first()
        elif performance_relation is not None and hasattr(performance_relation, "first"):
            latest_performance = performance_relation.first()

        report = {
            "portfolio_name": getattr(portfolio, "name", "Portfolio"),
            "report_type": report_type,
            "format": export_format,
            "nav": nav,
            "equity": equity,
            "balance": balance,
            "total_return": total_return,
            "allocation_count": allocations.count() if allocations is not None and hasattr(allocations, "count") else 0,
            "performance": getattr(latest_performance, "metrics", {}) or {},
        }
        if export_format == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(("metric", "value"))
            for key, value in report.items():
                if not isinstance(value, (dict, list, tuple)):
                    writer.writerow((key, value))
            report["serialized"] = output.getvalue()
        elif export_format != "json":
            raise ValueError("Unsupported report format: %s" % export_format)
        return report
