# Static analysis fixture only. Never import or execute this file.
import flask
application = flask.Flask(__name__)
# ruleid: codely.python.flask-debug
application.config["DEBUG"] = True
