# Static architecture rules fixture only. Never import or execute.
from order_service import OrderService


def calculate_tax(amount: int) -> float:
    _ = OrderService
    return amount * 0.1
