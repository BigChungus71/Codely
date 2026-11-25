# Static analysis fixture only. Never import or execute this file.
import yaml
def parse(data):
    # ruleid: codely.python.unsafe-yaml
    return yaml.load(data, Loader=yaml.Loader)
