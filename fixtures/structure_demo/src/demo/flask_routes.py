# Static fixture: never import or execute.
from flask import Blueprint as Group

blueprint = Group('private-name', __name__)


@blueprint.route('/private-route', methods=['POST'])
def submit():
    return None
