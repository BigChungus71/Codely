# Static analysis fixture only. Never import or execute this file.
import random
import secrets
def generate():
    reset_token = secrets.token_urlsafe(32)
    return reset_token
def simulation():
    sample = random.random()
    return sample
