# Static architecture rules fixture only. Never import or execute.
from fastapi import APIRouter
from order_service import OrderService

router = APIRouter()


@router.get('/orders')
def list_orders():
    return OrderService().list_orders()
