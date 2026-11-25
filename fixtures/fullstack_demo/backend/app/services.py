# Static fullstack demo fixture only. Never import or execute.
from .repository import OrderRepository


class OrderService:
    def list_orders(self, status: str):
        return OrderRepository().query_orders(status)
