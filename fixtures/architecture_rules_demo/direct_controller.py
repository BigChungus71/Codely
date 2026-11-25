# Static architecture rules fixture only. Never import or execute.
from flask import Blueprint
from order_repo import OrderRepository

blueprint = Blueprint('direct_orders', __name__)


@blueprint.route('/direct-orders', methods=['GET'])
def direct_orders():
    return OrderRepository().fetch_all()
