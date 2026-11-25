# Static analysis fixture only. Never import or execute this file.
import hashlib
def store(password):
    # ruleid: codely.python.weak-password-hash
    return hashlib.md5(password.encode()).hexdigest()
