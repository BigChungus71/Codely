# Static analysis fixture only. Never import or execute this file.
from yaml import load as parse_yaml, UnsafeLoader
def parse(data):
    # ruleid: codely.python.unsafe-yaml
    return parse_yaml(data, Loader=UnsafeLoader)
