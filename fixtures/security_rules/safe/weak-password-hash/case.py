# Static analysis fixture only. Never import or execute this file.
import hashlib
def store(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600000)
def checksum(data):
    return hashlib.sha256(data).hexdigest()
