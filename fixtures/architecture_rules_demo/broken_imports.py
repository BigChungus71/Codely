# Static architecture rules fixture only. Never import or execute.
from .missing_module import MissingThing


def broken_entry():
    return MissingThing
