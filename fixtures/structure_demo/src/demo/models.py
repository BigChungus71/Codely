# Static fixture: never import or execute.
from django.db import models


class Record(models.Model):
    pass
