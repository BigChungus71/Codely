# Static analysis fixture only. Never import or execute this file.
import requests
def fetch(url):
    return requests.get(url, verify=True, timeout=5)
def private_ca(url):
    return requests.get(url, verify="company-ca.pem", timeout=5)
