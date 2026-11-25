# Static analysis fixture only. Never import or execute this file.
from flask import Flask
app = Flask(__name__)
app.run(debug=False)
def unrelated(worker):
    worker.run(debug=True)
