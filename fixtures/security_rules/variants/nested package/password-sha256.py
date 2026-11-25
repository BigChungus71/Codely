# Static analysis fixture only. Never import or execute this file.
from hashlib import sha256
def store(user_password):
    # ruleid: codely.python.weak-password-hash
    return sha256(user_password.encode()).hexdigest()
