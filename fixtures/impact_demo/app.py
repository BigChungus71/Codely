# Static ASIM fixture only. Never import or execute.
from flask import Flask
from api import blueprint

app = Flask(__name__)
app.register_blueprint(blueprint)
