# Static fixture: never import or execute.
from fastapi.security import HTTPBearer

authentication = HTTPBearer()


def authenticated(function):
    return function
