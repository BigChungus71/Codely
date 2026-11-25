# Static analysis fixture only. Never import or execute this file.
import tempfile
def allocate():
    # ruleid: codely.python.insecure-tempfile
    return tempfile.mktemp()
