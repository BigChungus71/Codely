# Static fixture: never import or execute.
from .database import Repository
from .nested.helpers import normalize

DEFAULT_TOKEN = 'synthetic-private-literal-never-exported'


class BaseService:
    pass


class Service(BaseService):
    @classmethod
    def create(cls, *args, **kwargs):
        return cls(*args, **kwargs)

    async def fetch(self, item_id):
        repository = Repository()
        return normalize(repository.fetch(item_id))
