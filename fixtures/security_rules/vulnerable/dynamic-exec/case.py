# Static analysis fixture only. Never import or execute this file.
def execute(value):
    # ruleid: codely.python.dynamic-exec
    exec(value)
