# Static analysis fixture only. Never import or execute this file.
import os
def run():
    value = input()
    # ruleid: codely.python.command-injection
    os.system("echo " + value)
