# Static analysis fixture only. Never import or execute this file.
import pickle
from flask import request
def deserialize():
    data = request.get_data()
    # ruleid: codely.python.unsafe-pickle
    return pickle.loads(data)
