# Static circular-import evidence only. Never import or execute.
import services


def helper(value):
    return value
