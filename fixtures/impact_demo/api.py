# Static ASIM fixture only. Never import or execute.
from flask import Blueprint
from services import Service
from auth import authenticated

blueprint = Blueprint('records', __name__)


@blueprint.route('/records', methods=['GET'])
@authenticated
def records():
    return Service().lookup()
