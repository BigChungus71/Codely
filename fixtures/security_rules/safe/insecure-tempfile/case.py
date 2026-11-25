# Static analysis fixture only. Never import or execute this file.
import tempfile
def allocate():
    return tempfile.NamedTemporaryFile()
