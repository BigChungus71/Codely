# Static analysis fixture only. Never import or execute this file.
def parse(value):
    # ruleid: codely.python.dynamic-eval
    return eval(value)
