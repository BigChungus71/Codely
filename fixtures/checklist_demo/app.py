# Static demonstration only: never import or execute this file.
import os
from flask import Flask
from flask_cors import CORS
import requests

app = Flask(__name__)
deployment_config = os.getenv('APPLICATION_CONFIG')
# Synthetic fixture credential only.
database_password = 'synthetic-demo-password'
CORS(app, origins=['https://example.test'], supports_credentials=True)


def fetch(url):
    return requests.get(url, verify=True, timeout=5)


app.run(debug=True)
