from .dashboard import DashboardView
from .products import ProductsView
from .customers import CustomersView
from .billing import BillingView
from .coupons import CouponsView
from .analytics_views import (
    CalendarView, InsightsView, ReportsView, GSTView, BreakEvenView, AnalyticsPlusView
)
from .operations_views import (
    EndOfDayView, CashRegisterView, PurchaseOrdersView, RefundsView
)
from .people_views import (
    StaffView, TargetsView, HolidaysView, ExpensesView, RosterView, SalaryView
)
from .settings_view import SettingsView

__all__ = [
    "DashboardView",
    "ProductsView",
    "CustomersView",
    "BillingView",
    "CouponsView",
    "CalendarView",
    "InsightsView",
    "ReportsView",
    "GSTView",
    "BreakEvenView",
    "AnalyticsPlusView",
    "EndOfDayView",
    "CashRegisterView",
    "PurchaseOrdersView",
    "RefundsView",
    "StaffView",
    "TargetsView",
    "HolidaysView",
    "ExpensesView",
    "RosterView",
    "SalaryView",
    "SettingsView",
]
