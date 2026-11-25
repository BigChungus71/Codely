# Static analysis fixture only. Never import or execute this file.
from flask import Flask
app = Flask(__name__)
# ruleid: codely.python.flask-debug
app.run(debug=True)
