# Static analysis fixture only. Never import or execute this file.
import json
import pickle
from flask import request
def deserialize():
    return json.loads(request.get_data())
def local_roundtrip():
    return pickle.loads(pickle.dumps({"count": 1}))
