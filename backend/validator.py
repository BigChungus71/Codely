"""
CodeRAG Hallucination & Confidence Checker
============================================
Validates LLM-generated code against retrieved context to detect
hallucinated imports, functions, classes, and APIs.
Returns structured confidence data with green/yellow/red severity levels.
"""

import re


def check_hallucinations_detailed(answer: str, chunks: list[dict]) -> dict:
    """
    Deep validation of LLM answer against retrieved source chunks.
    Returns structured confidence report:
    {
        "overall_confidence": 0.0 - 1.0,
        "level": "high" | "medium" | "low",
        "verified": [{"symbol": "...", "type": "..."}],
        "warnings": [{"symbol": "...", "type": "...", "reason": "..."}],
        "errors": [{"symbol": "...", "type": "...", "reason": "..."}],
        "stats": {"total_symbols": N, "verified_count": N, "warning_count": N, "error_count": N}
    }
    """
    chunk_text = "\n".join(c["text"] for c in chunks)

    verified = []
    warnings = []
    errors = []

    # ── Standard Library / Builtins (skip these) ────────────────────────────
    STDLIB = {
        "os", "sys", "re", "json", "time", "math", "random",
        "pathlib", "typing", "collections", "itertools",
        "subprocess", "logging", "datetime", "functools",
        "io", "abc", "copy", "hashlib", "uuid", "base64",
        "threading", "multiprocessing", "asyncio", "dataclasses",
        "enum", "contextlib", "operator", "string", "textwrap",
        "unittest", "pytest", "http", "urllib", "socket",
        "csv", "pickle", "struct", "tempfile", "shutil",
        "glob", "fnmatch", "argparse", "configparser",
    }

    BUILTIN_FUNCTIONS = {
        "print", "len", "range", "str", "int", "float", "list", "dict",
        "tuple", "set", "bool", "bytes", "bytearray", "memoryview",
        "open", "type", "isinstance", "issubclass", "enumerate", "zip",
        "map", "filter", "sorted", "reversed", "any", "all", "sum",
        "min", "max", "abs", "round", "format", "input", "repr",
        "hash", "id", "dir", "vars", "getattr", "setattr", "hasattr",
        "delattr", "callable", "iter", "next", "super", "property",
        "staticmethod", "classmethod", "object", "Exception",
        "ValueError", "TypeError", "KeyError", "IndexError",
        "AttributeError", "ImportError", "FileNotFoundError",
        "RuntimeError", "StopIteration", "NotImplementedError",
    }

    JS_BUILTINS = {
        "console", "log", "warn", "error", "require", "module",
        "exports", "process", "setTimeout", "setInterval",
        "clearTimeout", "clearInterval", "Promise", "Array",
        "Object", "String", "Number", "Boolean", "Date", "Math",
        "JSON", "Map", "Set", "RegExp", "Symbol", "Error",
        "fetch", "async", "await", "then", "catch", "finally",
        "parseInt", "parseFloat", "isNaN", "encodeURIComponent",
        "decodeURIComponent", "document", "window", "alert",
    }

    ALL_SKIP = STDLIB | BUILTIN_FUNCTIONS | JS_BUILTINS

    # ── 1. Check Imports ────────────────────────────────────────────────────
    import_patterns = [
        r"(?:import|from)\s+([\w.]+)",
        r"require\(['\"]([^'\"]+)['\"]\)",
        r"import\s+.*\s+from\s+['\"]([^'\"]+)",
    ]

    found_imports = set()
    for pattern in import_patterns:
        found_imports.update(re.findall(pattern, answer))

    for imp in found_imports:
        root_module = imp.split(".")[0]
        if root_module in ALL_SKIP:
            verified.append({"symbol": imp, "type": "import"})
            continue
        if imp in chunk_text or root_module in chunk_text:
            verified.append({"symbol": imp, "type": "import"})
        else:
            errors.append({
                "symbol": imp,
                "type": "import",
                "reason": f"Module '{imp}' not found in retrieved codebase context"
            })

    # ── 2. Check Function Calls ─────────────────────────────────────────────
    fn_calls = set(re.findall(r'\b([a-z_][a-zA-Z0-9_]*)\s*\(', answer))
    for fn in fn_calls:
        if fn in ALL_SKIP:
            continue
        if fn in chunk_text:
            verified.append({"symbol": f"{fn}()", "type": "function"})
        else:
            warnings.append({
                "symbol": f"{fn}()",
                "type": "function",
                "reason": f"Function '{fn}()' not found in retrieved context — may be hallucinated"
            })

    # ── 3. Check Class References ───────────────────────────────────────────
    class_refs = set(re.findall(r'\b([A-Z][a-zA-Z0-9_]+)\b', answer))
    for cls in class_refs:
        if cls in ALL_SKIP or len(cls) <= 2:
            continue
        if cls in chunk_text:
            verified.append({"symbol": cls, "type": "class"})
        else:
            # Classes are warnings not errors (could be from installed packages)
            warnings.append({
                "symbol": cls,
                "type": "class",
                "reason": f"Class '{cls}' not found in retrieved context — verify it exists"
            })

    # ── 4. Check Decorator Usage ────────────────────────────────────────────
    decorators = set(re.findall(r'@(\w+)', answer))
    for dec in decorators:
        if dec in {"property", "staticmethod", "classmethod", "abstractmethod", "override"}:
            verified.append({"symbol": f"@{dec}", "type": "decorator"})
        elif dec in chunk_text:
            verified.append({"symbol": f"@{dec}", "type": "decorator"})
        else:
            warnings.append({
                "symbol": f"@{dec}",
                "type": "decorator",
                "reason": f"Decorator '@{dec}' not found in retrieved context"
            })

    # ── Calculate Confidence Score ──────────────────────────────────────────
    total = len(verified) + len(warnings) + len(errors)
    if total == 0:
        overall = 1.0
    else:
        # Verified = full credit, warnings = half, errors = zero
        score = (len(verified) * 1.0 + len(warnings) * 0.4) / total
        overall = round(min(max(score, 0.0), 1.0), 2)

    if overall >= 0.75:
        level = "high"
    elif overall >= 0.45:
        level = "medium"
    else:
        level = "low"

    return {
        "overall_confidence": overall,
        "level": level,
        "verified": verified,
        "warnings": warnings,
        "errors": errors,
        "stats": {
            "total_symbols": total,
            "verified_count": len(verified),
            "warning_count": len(warnings),
            "error_count": len(errors)
        }
    }


def check_hallucinations(answer: str, chunks: list[dict]) -> list[str]:
    """
    Legacy wrapper — returns flat list of warning strings.
    Used by existing /query endpoint for backward compatibility.
    """
    report = check_hallucinations_detailed(answer, chunks)
    flat_warnings = []
    for w in report["warnings"]:
        flat_warnings.append(f"⚠ {w['symbol']} — {w['reason']}")
    for e in report["errors"]:
        flat_warnings.append(f"❌ {e['symbol']} — {e['reason']}")
    return flat_warnings


def lint_python(code: str) -> str:
    """Run pylint on a code string, return output."""
    import subprocess
    try:
        result = subprocess.run(
            [
                "pylint",
                "--from-stdin",
                "--disable=C,R,W0611",
                "--score=no"
            ],
            input=code,
            capture_output=True,
            text=True,
            timeout=15
        )
        output = result.stdout.strip()
        return output if output else "No issues found."
    except FileNotFoundError:
        return "pylint not installed — run: pip install pylint"
    except subprocess.TimeoutExpired:
        return "Lint timed out."


def lint_code(code: str, lang: str = "python") -> str:
    """Route to the right linter based on language."""
    if lang == "python":
        return lint_python(code)
    return f"Linting not yet supported for '{lang}'"
