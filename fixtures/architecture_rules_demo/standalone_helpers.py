# Static architecture rules fixture only. Never import or execute.
def normalize_label(label: str) -> str:
    return label.strip().lower()
