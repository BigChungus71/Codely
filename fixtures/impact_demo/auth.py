# Static ASIM fixture only. No authentication flow is executed.
from flask_login import login_required


def authenticated(function):
    return login_required(function)
