"""Bounded static multi-language discovery. No target modules are imported or executed."""
import ast
from dataclasses import dataclass, field
import io
import os
from pathlib import Path
import tokenize

from .semgrep_adapter import EXCLUDED, _linked
from .structure_languages import (
    SUPPORTED_CODE_LANGUAGES,
    classify_file,
    count_ts_nodes,
    inspect_config_metadata,
    make_parser,
)


DEFAULT_EXCLUSIONS = tuple(sorted(EXCLUDED | {
    'env', '.tox', '.mypy_cache', '.ruff_cache', '.cache', '.eggs', 'site-packages',
    'vendor', 'third_party', '.idea', '.vscode', '.next', 'coverage', 'htmlcov',
    '.pytest_cache', '__pypackages__'}))


@dataclass(frozen=True)
class StructureOptions:
    max_files: int = 5000
    max_file_bytes: int = 1024 * 1024
    max_repository_bytes: int = 50 * 1024 * 1024
    max_entries: int = 50000
    max_ast_nodes: int = 200000
    max_repository_ast_nodes: int = 1000000
    source_roots: tuple[str, ...] = ()
    external_modules: tuple[str, ...] = ()
    excluded_directories: tuple[str, ...] = DEFAULT_EXCLUSIONS
    languages: tuple[str, ...] = ('python', 'java', 'javascript', 'jsx', 'typescript', 'tsx')

    def validate(self):
        for key in ('max_files', 'max_file_bytes', 'max_repository_bytes', 'max_entries', 'max_ast_nodes',
                    'max_repository_ast_nodes'):
            if type(getattr(self, key)) is not int or getattr(self, key) < 1:
                raise ValueError('Limits must be positive integers')
        for root in self.source_roots:
            path = Path(root.replace('\\', '/'))
            if path.is_absolute() or '..' in path.parts or ':' in root or root.startswith('\\'):
                raise ValueError('Source roots must be repository-relative')
        if not self.languages or not all(lang in SUPPORTED_CODE_LANGUAGES for lang in self.languages):
            raise ValueError('Unsupported language in StructureOptions.languages')


@dataclass
class Discovery:
    valid: bool = True
    files: list[dict] = field(default_factory=list)
    trees: dict[str, ast.Module] = field(default_factory=dict)
    ts_trees: dict[str, object] = field(default_factory=dict)
    sources: dict[str, bytes] = field(default_factory=dict)
    languages: dict[str, str] = field(default_factory=dict)
    config_files: list[dict] = field(default_factory=list)
    diagnostics: list[dict] = field(default_factory=list)
    excluded: list[dict] = field(default_factory=list)
    bytes_read: int = 0
    unsupported_files: int = 0
    visited_entries: int = 0
    ast_nodes: int = 0


def _first_ts_error_line(root_node) -> int | None:
    stack = [root_node]
    while stack:
        node = stack.pop()
        if node.is_error or node.is_missing:
            return node.start_point[0] + 1
        if node.has_error:
            stack.extend(reversed(node.children))
    return None


def discover(project_path, options):
    result = Discovery()
    options.validate()
    try:
        if not isinstance(project_path, str) or not project_path.strip() or '\x00' in project_path:
            raise ValueError('invalid')
        requested = Path(project_path)
        if not requested.is_dir() or _linked(requested):
            raise ValueError('invalid')
        root = requested.resolve()
    except (OSError, ValueError):
        result.valid = False
        result.diagnostics.append({'code': 'invalid_repository'})
        return result

    def walk_error(error):
        item = {'code': 'directory_unreadable'}
        try:
            item['file'] = Path(error.filename).relative_to(root).as_posix()
        except (ValueError, TypeError):
            pass
        result.diagnostics.append(item)

    def skipped(record, code):
        record['status'] = code
        result.diagnostics.append({'code': code, 'file': record['file']})

    try:
        for folder, dirs, files in os.walk(root, followlinks=False, onerror=walk_error):
            dirs.sort()
            for directory in dirs[:]:
                path = Path(folder) / directory
                relative = path.relative_to(root).as_posix()
                if directory in set(DEFAULT_EXCLUSIONS) | set(options.excluded_directories):
                    dirs.remove(directory)
                    result.excluded.append({'file': relative, 'reason': 'excluded_directory'})
                elif _linked(path) or not path.resolve().is_relative_to(root):
                    dirs.remove(directory)
                    result.diagnostics.append({'code': 'linked_directory_skipped', 'file': relative})
            for name in sorted(files):
                result.visited_entries += 1
                if result.visited_entries > options.max_entries:
                    result.diagnostics.append({'code': 'entry_limit'})
                    return result
                path = Path(folder) / name
                relative = path.relative_to(root).as_posix()
                category, lang = classify_file(relative)
                if category == 'ignored_bundle':
                    continue
                if category == 'config':
                    if not _linked(path) and path.resolve().is_relative_to(root):
                        try:
                            size = path.stat().st_size
                            if size <= options.max_file_bytes and result.bytes_read + size <= options.max_repository_bytes:
                                content = path.read_bytes()
                                text = content.decode('utf-8-sig', errors='replace')
                                result.config_files.append(inspect_config_metadata(relative, text))
                            else:
                                result.config_files.append({'file': relative, 'kind': lang, 'package_managers': [], 'frameworks': [], 'dependencies': [], 'tsconfig': None})
                        except OSError:
                            pass
                    continue
                if category != 'code' or lang not in options.languages:
                    result.unsupported_files += 1
                    continue
                if len(result.files) >= options.max_files:
                    result.diagnostics.append({'code': 'file_count_limit', 'file': relative})
                    return result
                record = {'file': relative, 'status': 'pending', 'size_bytes': 0}
                if lang != 'python':
                    record['language'] = lang
                result.files.append(record)
                try:
                    if _linked(path) or not path.resolve().is_relative_to(root):
                        skipped(record, 'linked_file_skipped')
                        continue
                    record['size_bytes'] = path.stat().st_size
                    if record['size_bytes'] > options.max_file_bytes:
                        skipped(record, 'file_size_limit')
                        continue
                    if result.bytes_read + record['size_bytes'] > options.max_repository_bytes:
                        skipped(record, 'repository_size_limit')
                        continue
                    with path.open('rb') as source:
                        content = source.read(min(options.max_file_bytes + 1,
                            options.max_repository_bytes - result.bytes_read + 1))
                    result.bytes_read += len(content)
                    if len(content) > options.max_file_bytes or result.bytes_read > options.max_repository_bytes:
                        skipped(record, 'source_changed_or_byte_limit')
                        return result
                    if lang == 'python':
                        try:
                            encoding, _ = tokenize.detect_encoding(io.BytesIO(content).readline)
                        except SyntaxError:
                            skipped(record, 'encoding_error')
                            continue
                        text = content.decode(encoding)
                        record['encoding'] = encoding
                        record['line_count'] = len(text.splitlines())
                        tree = ast.parse(text)
                        nodes = sum(1 for _ in ast.walk(tree))
                        if nodes > options.max_ast_nodes:
                            skipped(record, 'ast_node_limit')
                            continue
                        if result.ast_nodes + nodes > options.max_repository_ast_nodes:
                            skipped(record, 'repository_ast_node_limit')
                            continue
                        result.ast_nodes += nodes
                        result.trees[relative] = tree
                        result.languages[relative] = 'python'
                        record['status'] = 'parsed'
                    else:
                        text = content.decode('utf-8-sig')
                        utf8_bytes = text.encode('utf-8')
                        record['encoding'] = 'utf-8'
                        record['line_count'] = len(text.splitlines())
                        parser = make_parser(lang)
                        ts_tree = parser.parse(utf8_bytes)
                        nodes, exceeded = count_ts_nodes(ts_tree.root_node, options.max_ast_nodes)
                        if exceeded:
                            skipped(record, 'ast_node_limit')
                            continue
                        if result.ast_nodes + nodes > options.max_repository_ast_nodes:
                            skipped(record, 'repository_ast_node_limit')
                            continue
                        if ts_tree.root_node.has_error:
                            skipped(record, 'syntax_error')
                            err_line = _first_ts_error_line(ts_tree.root_node)
                            if err_line:
                                result.diagnostics[-1]['start_line'] = err_line
                            continue
                        result.ast_nodes += nodes
                        result.ts_trees[relative] = ts_tree.root_node
                        result.sources[relative] = utf8_bytes
                        result.languages[relative] = lang
                        record['status'] = 'parsed'
                except (UnicodeError, LookupError):
                    skipped(record, 'encoding_error')
                except SyntaxError as error:
                    skipped(record, 'syntax_error')
                    if error.lineno:
                        result.diagnostics[-1]['start_line'] = error.lineno
                except (RecursionError, ValueError):
                    skipped(record, 'parser_limit_or_invalid_source')
                except OSError:
                    skipped(record, 'file_unreadable')
    except OSError:
        result.diagnostics.append({'code': 'discovery_failed'})
    return result
