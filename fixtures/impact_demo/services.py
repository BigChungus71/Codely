# Static ASIM fixture only. Never import or execute.
from database import Repository
from cycle import helper


class Service:
    def lookup(self):
        return helper(Repository().lookup())
