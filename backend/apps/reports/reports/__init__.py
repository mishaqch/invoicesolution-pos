"""Importing this package side-effects-registers every report.

Add new reports here so they're discoverable by the registry without
the views having to import each one.
"""

from . import (  # noqa: F401
    audit_log,
    branch_comparison,
    cashier_performance,
    category_wise,
    customer_dormant,
    customer_top_n,
    daily_sales,
    fbr_submissions,
    hourly_heatmap,
    item_wise,
    movers,
    payment_breakdown,
    profit_loss,
    returns_analysis,
    stock,
    stock_aging,
    supplier_purchase,
    tax,
)
