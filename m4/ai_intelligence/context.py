import ast
from functools import lru_cache
import importlib
from collections import Counter
from dataclasses import dataclass
import os
from pathlib import Path
import re
import stat
from typing import Protocol

from .contracts import Evidence, SourceRange
from .gemini import ProviderError


EXTENSIONS = {
    ".java", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".py", ".yaml",
    ".yml", ".toml", ".json", ".xml", ".properties", ".gradle", ".sql",
}
SKIP = {
    "node_modules", "vendor", "target", "build", "dist", "out", "coverage", "venv",
    "generated", "fixtures", "secrets", "credentials", "uploads", "site-packages",
    "__pycache__", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
}
SENSITIVE_NAME = re.compile(r"(^|[._-])(env|secret[s]?|credential[s]?|keystore|private[-_]key)([._-]|$)", re.I)
SECRET_ASSIGNMENT = re.compile(
    r"""(?ix)["']?[\w.-]*(?:api[_-]?key|token|password|client[_-]?secret|authorization|passwd|secret|database[_-]?url)["']?
        \s*[:=]\s*(?:"[^"]*"|'[^']*'|[^\s,;}]+)"""
)
SECRET_VALUE = re.compile(
    r"(?i)AIza[0-9A-Za-z_-]{35}|gsk_[0-9A-Za-z_-]{12,}|sk-[0-9A-Za-z_-]{12,}|"
    r"gh[pousr]_[0-9A-Za-z_]{12,}|AKIA[0-9A-Z]{16}|"
    r"eyJ[0-9a-z_-]+\.[0-9a-z_-]+\.[0-9a-z_-]+|"
    r"[\w+]+://[^\s/@:]+:[^\s/@]+@|bearer\s+[0-9a-z._~+/-]{12,}"
)
REDACTED = "[REDACTED SOURCE LINE]"
TOKEN = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]{2,}")
IMPORT = re.compile(r"^\s*(?:import\b|from\s+\S+\s+import\b|export\b.*\bfrom\b|\S.*\brequire\s*\()")
DECLARATION = re.compile(r"\b(?:class|interface|enum|record|function|def|type|const)\s+([A-Za-z_$][\w$]*)")
STOP = set("this public private static final protected class function return import const true false void string null self export".split())


class ContextError(ValueError):
    pass


class Embedder(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


def redact(line: str) -> str:
    if SECRET_VALUE.search(line):
        return REDACTED
    for match in SECRET_ASSIGNMENT.finditer(line):
        value = re.split(r"[:=]", match.group(), maxsplit=1)[1].strip().strip("'\042")
        if value and not re.fullmatch(r"\$\{[A-Z_][A-Z0-9_.-]*\}", value):
            return REDACTED
    return line


@dataclass(frozen=True)
class Source:
    lines: tuple[str, ...]
    spans: tuple[tuple[int, int], ...]
    redacted_lines: frozenset[int]
    newline: str
    final_newline: bool
    patchable_line_endings: bool


@lru_cache(maxsize=5)
def _language(suffix):
    flavors = {
        ".java": ("java", "language"),
        ".ts": ("typescript", "language_typescript"),
        ".tsx": ("typescript", "language_tsx"),
        ".js": ("javascript", "language"),
        ".jsx": ("javascript", "language"),
    }
    if suffix not in flavors:
        return None
    try:
        from tree_sitter import Language
        module, name = flavors[suffix]
        return Language(getattr(importlib.import_module("tree_sitter_" + module), name)())
    except (ImportError, AttributeError, TypeError, ValueError):
        return None


def _native_spans(path, text):
    suffix = Path(path).suffix.lower()
    if suffix in {".mjs", ".cjs"}:
        suffix = ".js"
    language = _language(suffix)
    if language is None:
        return ()
    from tree_sitter import Parser

    tree = Parser(language).parse(text.encode("utf-8"))
    kinds = {
        "class_declaration", "abstract_class_declaration", "interface_declaration",
        "record_declaration", "enum_declaration", "method_declaration",
        "constructor_declaration", "method_definition", "function_declaration",
        "generator_function_declaration", "arrow_function",
    }
    result = set()
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type in kinds and not node.has_error:
            start = node.start_point.row + 1
            end = node.end_point.row + int(node.end_point.column > 0)
            if end >= start:
                result.add((start, end))
        stack.extend(node.named_children)
    return tuple(sorted(result))


def parsed_spans(path: str, text: str) -> tuple[tuple[int, int], ...]:
    if not path.endswith(".py"):
        return _native_spans(path, text)
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError):
        return ()
    kinds = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    return tuple(sorted(
        (min([node.lineno] + [item.lineno for item in node.decorator_list]), node.end_lineno)
        for node in ast.walk(tree) if isinstance(node, kinds) and node.end_lineno
    ))


def chunk_ranges(source: Source):
    covered = bytearray(len(source.lines))
    for start, end in source.spans:
        if end - start < 50 and not any(covered[start - 1:end]):
            yield start, end
            covered[start - 1:end] = b"\1" * (end - start + 1)
    cursor = 0
    while cursor < len(covered):
        if covered[cursor]:
            cursor += 1
            continue
        end = cursor
        while end < len(covered) and not covered[end] and end - cursor < 40:
            end += 1
        yield cursor + 1, end
        cursor = end


class SemanticIndex:
    """An in-memory FAISS index tied to one source snapshot."""

    def __init__(self, embedder: Embedder, chunks: list[Evidence]):
        import faiss
        import numpy as np

        self._np = np
        self._embedder = embedder
        matrix = self._matrix(embedder.embed_documents(
            [f"{chunk.path}\n{chunk.text}" for chunk in chunks]
        ), len(chunks))
        self._index = faiss.IndexFlatIP(matrix.shape[1])
        self._index.add(matrix)

    def _matrix(self, vectors, count):
        np = self._np
        matrix = np.ascontiguousarray(vectors, dtype=np.float32)
        if (matrix.ndim != 2 or matrix.shape[0] != count or not matrix.shape[1]
                or not np.isfinite(matrix).all()):
            raise ValueError("Invalid embedding shape or values")
        lengths = np.linalg.norm(matrix, axis=1, keepdims=True)
        if not np.isfinite(lengths).all() or (lengths <= 0).any():
            raise ValueError("Invalid embedding norm")
        return matrix / lengths

    def search(self, query: str, limit: int):
        vector = self._matrix([self._embedder.embed_query(query)], 1)
        if vector.shape[1] != self._index.d:
            raise ValueError("Embedding dimensions differ")
        scores, indexes = self._index.search(vector, min(limit, self._index.ntotal))
        return [(int(number), float(score)) for number, score in zip(indexes[0], scores[0])
                if number >= 0]


class RepositoryContext:
    def __init__(self, project_id: str, root: Path, *, embedder: Embedder | None = None,
                 revision: str | None = None):
        if not project_id or not Path(root).is_dir():
            raise ContextError("A project ID and repository directory are required")
        self.project_id = project_id
        self.revision = revision
        self.files: dict[str, Source] = {}
        self.skipped = Counter()
        self.chunks: list[Evidence] = []
        self.symbols: dict[str, list[int]] = {}
        self.semantic_status = "disabled"
        self.semantic = None
        self._snapshot(Path(root).resolve())
        self.words = [set(TOKEN.findall(chunk.text.lower())) - STOP for chunk in self.chunks]
        if embedder is not None and self.chunks:
            try:
                self.semantic = SemanticIndex(embedder, self.chunks)
                self.semantic_status = "ready"
            except (ImportError, OSError, ProviderError, ValueError, TypeError, RuntimeError):
                self.semantic_status = "unavailable"

    def _snapshot(self, root: Path):
        total_bytes = 0
        for directory, dirs, files in os.walk(root, followlinks=False):
            base = Path(directory)
            dirs[:] = sorted(name for name in dirs if self._allowed(name) and not (base / name).is_symlink())
            for name in sorted(files):
                path = base / name
                if not self._allowed(name) or path.suffix.lower() not in EXTENSIONS:
                    continue
                if path.is_symlink() or not path.is_file():
                    continue
                try:
                    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
                    with os.fdopen(os.open(path, flags), "rb") as stream:
                        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                            continue
                        raw = stream.read(160_001)
                    if len(raw) > 160_000 or b"\0" in raw:
                        self.skipped["large_or_binary"] += 1
                        continue
                    text = raw.decode("utf-8")
                except (OSError, UnicodeError):
                    self.skipped["unreadable"] += 1
                    continue
                if "PRIVATE KEY-----" in text:
                    self.skipped["private_key_material"] += 1
                    continue
                if total_bytes + len(raw) > 8_000_000 or len(self.files) >= 2_000:
                    self.skipped["snapshot_limit"] += 1
                    continue
                total_bytes += len(raw)
                rel = path.relative_to(root).as_posix()
                try:
                    SourceRange(path=rel, start_line=1, end_line=1)
                except ValueError:
                    self.skipped["invalid_path"] += 1
                    continue
                normalized = text.replace("\r\n", "\n").replace("\r", "\n")
                lines = tuple(redact(line) for line in normalized.split("\n"))
                final_newline = text.endswith(("\n", "\r"))
                lines = lines[:-1] if final_newline else lines
                without_crlf = text.replace("\r\n", "")
                self.files[rel] = Source(
                    lines, parsed_spans(rel, normalized),
                    frozenset(i for i, line in enumerate(lines, 1) if line == REDACTED),
                    "\r\n" if "\r\n" in text else "\n", final_newline,
                    "\r" not in without_crlf and not ("\r\n" in text and "\n" in without_crlf),
                )
                for start, end in chunk_ranges(self.files[rel]):
                    evidence = self._evidence(rel, start, end, "keyword")
                    if not evidence.text.strip() or len(evidence.text) > 10_000:
                        continue
                    for name in set(DECLARATION.findall(evidence.text)):
                        self.symbols.setdefault(name, []).append(len(self.chunks))
                    self.chunks.append(evidence)

    @staticmethod
    def _allowed(name):
        return not (name.startswith(".") or name.lower() in SKIP or SENSITIVE_NAME.search(name))

    def _evidence(self, path, start, end, reason):
        source = self.files[path]
        return Evidence(id=f"{path}:{start}-{end}", path=path, start_line=start, end_line=end,
                        text="\n".join(source.lines[start - 1:end]), reason=reason,
                        redacted=any(i in source.redacted_lines for i in range(start, end + 1)))

    def retrieve(self, target: SourceRange, query: str = "", *, budget: int = 18_000,
                 include_related: bool = True) -> list[Evidence]:
        if not 0 < budget <= 32_000:
            raise ContextError("Context budget is outside the supported range")
        source = self.files.get(target.path)
        if not source or target.end_line > len(source.lines):
            raise ContextError("Scanner range is outside the indexed source snapshot")
        exact = self._evidence(target.path, target.start_line, target.end_line, "affected")
        remaining = budget
        results = {}

        def add(item):
            nonlocal remaining
            cost = len(item.text) + 2 * len(item.path) + 180
            if cost <= remaining and item.id not in results and len(results) < 14:
                results[item.id] = item
                remaining -= cost

        add(exact)
        if not results:
            raise ContextError("Exact affected range exceeds the context budget")
        if not include_related:
            return [exact]
        spans = [(start, end) for start, end in source.spans
                 if start <= target.start_line <= target.end_line <= end]
        if spans:
            start, end = min(spans, key=lambda span: span[1] - span[0])
            add(self._evidence(target.path, start, end, "containing"))
        first = max(1, target.start_line - 7)
        last = min(len(source.lines), target.end_line + 7)
        add(self._evidence(target.path, first, last, "containing"))
        import_lines = []
        for number, line in enumerate(source.lines[:120], 1):
            if IMPORT.match(line):
                import_lines.append(line)
                add(self._evidence(target.path, number, number, "imports"))
                if len(import_lines) == 3:
                    break
        query_text = redact(query[:4_000]) + "\n" + exact.text
        names = set(TOKEN.findall(query_text + "\n" + "\n".join(import_lines)))
        frequencies = Counter(index for name in names for index in self.symbols.get(name, ())
                              if self.chunks[index].path != target.path)
        for index, _ in sorted(
                frequencies.items(), key=lambda item: (-item[1], item[0]))[:3]:
            add(self.chunks[index].model_copy(update={"reason": "symbol"}))
        if self.semantic is not None:
            try:
                for index, score in self.semantic.search(query_text[:8_000], 5):
                    add(self.chunks[index].model_copy(update={"reason": "semantic", "similarity": score}))
            except (ProviderError, ValueError, TypeError, RuntimeError):
                pass
        words = {word.lower() for word in names} - STOP
        ranked = sorted(range(len(self.chunks)), key=lambda i: (
            -len(words & self.words[i]), self.chunks[i].path == target.path, i
        ))
        for index in ranked[:8]:
            if words & self.words[index]:
                add(self.chunks[index])
        return list(results.values())
