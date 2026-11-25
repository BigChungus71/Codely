# Static analysis fixture only. Never import or execute this file.
import requests
def fetch(url):
    # ruleid: codely.python.tls-verification-disabled
    return requests.get(url, verify=False, timeout=5)
