# Static analysis fixture only. Never import or execute this file.
import httpx
def client():
    # ruleid: codely.python.tls-verification-disabled
    return httpx.Client(verify=False)
