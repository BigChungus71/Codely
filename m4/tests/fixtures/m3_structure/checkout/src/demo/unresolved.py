# Static fixture: never import or execute.
import missing_demo_dependency
from .missing import Absent
import importlib as loader

loaded = loader.import_module('private-dynamic-module-name')
