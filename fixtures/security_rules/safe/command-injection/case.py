# Static analysis fixture only. Never import or execute this file.
import subprocess
from flask import request
def ping():
    host = request.args.get("host")
    subprocess.run(["ping", host], shell=False, timeout=5)
    subprocess.run("echo fixed", shell=True, timeout=5)
