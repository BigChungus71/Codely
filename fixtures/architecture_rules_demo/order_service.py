# Static architecture rules fixture only. Never import or execute.
from order_repo import OrderRepository
from billing_service import calculate_tax


class OrderService:
    def list_orders(self):
        rows = OrderRepository().fetch_all()
        return {'rows': rows, 'tax': calculate_tax(100)}
