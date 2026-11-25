# Static analysis fixture only. Never import or execute this file.
import random
def generate():
    # ruleid: codely.python.insecure-security-random
    reset_token = str(random.randint(100000, 999999))
    return reset_token
