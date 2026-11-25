# Static fixture: never import or execute.
from fastapi import APIRouter as Router
from .services import Service as Worker
from .auth import authenticated

router = Router()


@router.get('/redacted-example')
@authenticated
async def read_item(item_id: int, /, limit: int = 10, *, optional=None, **kwargs):
    worker = Worker()
    return await worker.fetch(item_id)
