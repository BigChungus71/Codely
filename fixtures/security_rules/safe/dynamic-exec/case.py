# Static analysis fixture only. Never import or execute this file.
def execute(value):
    operations = {"lower": str.lower}
    return operations["lower"](value)
