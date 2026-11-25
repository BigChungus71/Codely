# Static fullstack demo fixture only. Never import or execute.
from fastapi import APIRouter
from .services import OrderService

router = APIRouter()


@router.get('/api/orders')
def get_orders(status: str):
    return OrderService().list_orders(status)
