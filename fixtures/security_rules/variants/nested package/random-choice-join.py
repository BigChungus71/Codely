# Static analysis fixture only. Never import or execute this file.
import random
def generate():
    # ruleid: codely.python.insecure-security-random
    api_key = "".join(random.choice("abcd") for _ in range(20))
    return api_key
