# Static analysis fixture only. Never import or execute this file.
import subprocess
from flask import request
def ping():
    host = request.args.get("host")
    command = "ping " + host
    # ruleid: codely.python.command-injection
    subprocess.run(command, shell=True, timeout=5)
