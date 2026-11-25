# Static analysis fixture only. Never import or execute this file.
import yaml
def parse(data):
    return yaml.safe_load(data)
def explicit(data):
    return yaml.load(data, Loader=yaml.SafeLoader)
