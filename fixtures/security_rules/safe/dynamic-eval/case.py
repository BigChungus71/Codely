# Static analysis fixture only. Never import or execute this file.
import ast
def parse(value):
    return ast.literal_eval(value)
