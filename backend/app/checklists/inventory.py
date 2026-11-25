"""Bounded read-only inventory for configuration indicators, not a code graph."""
import ast
from dataclasses import dataclass, field
import os
from pathlib import Path

from ..analyzers.semgrep_adapter import EXCLUDED, MAX_FILES, MAX_FILE_BYTES, MAX_TOTAL_BYTES, _linked


def evidence(file, kind, node=None):
    item = {'file': file, 'kind': kind}
    if node is not None:
        item.update(start_line=node.lineno, end_line=getattr(node, 'end_lineno', node.lineno))
    return item


def sensitive(path):
    name = path.name.lower()
    return ((name == '.env' or name.startswith('.env.'))
            and name not in {'.env.example', '.env.sample', '.env.template'}) or (
            path.suffix.lower() in {'.key', '.pem', '.p12', '.pfx'}
            or name in {'id_rsa', 'id_ed25519'})


def manifest(path):
    name = path.name.lower()
    return (name.startswith('requirements') and path.suffix.lower() == '.txt') or name in {
        'pyproject.toml', 'pipfile', 'setup.py', 'setup.cfg'}


@dataclass
class Inventory:
    root: Path | None = None
    paths: list[str] = field(default_factory=list)
    texts: dict[str, str] = field(default_factory=dict)
    trees: dict[str, ast.Module] = field(default_factory=dict)
    diagnostics: list[dict] = field(default_factory=list)
    valid: bool = True

    @property
    def complete(self):
        return self.valid and not self.diagnostics


def inspect_repository(project_path):
    result = Inventory()
    try:
        if not isinstance(project_path, str) or not project_path.strip() or '\x00' in project_path:
            raise ValueError('invalid')
        root = Path(project_path)
        if not root.is_dir() or _linked(root):
            raise ValueError('invalid')
        result.root = root.resolve()
    except (OSError, ValueError):
        result.valid = False
        result.diagnostics.append({'code': 'invalid_repository'})
        return result
    byte_count = 0

    def walk_error(_error):
        result.diagnostics.append({'code': 'directory_unreadable'})

    try:
        for folder, dirs, files in os.walk(result.root, followlinks=False, onerror=walk_error):
            dirs.sort()
            for directory in dirs[:]:
                path = Path(folder) / directory
                if directory in EXCLUDED:
                    dirs.remove(directory)
                elif _linked(path):
                    dirs.remove(directory)
                    result.diagnostics.append({'code': 'linked_directory_skipped',
                        'file': path.relative_to(result.root).as_posix()})
            for name in sorted(files):
                path = Path(folder) / name
                relative = path.relative_to(result.root).as_posix()
                if len(result.paths) >= MAX_FILES:
                    result.diagnostics.append({'code': 'file_inventory_limit'})
                    return result
                if _linked(path) or not path.resolve().is_relative_to(result.root):
                    result.diagnostics.append({'code': 'linked_file_skipped', 'file': relative})
                    continue
                result.paths.append(relative)
                # Secret-named files are presence indicators only: never read values.
                if sensitive(path):
                    continue
                relevant = (path.suffix.lower() == '.py' or manifest(path)
                            or name == '.gitignore' or name.lower().startswith('dockerfile'))
                if not relevant:
                    continue
                try:
                    with path.open('rb') as source:
                        content = source.read(MAX_FILE_BYTES + 1)
                    if len(content) > MAX_FILE_BYTES or byte_count + len(content) > MAX_TOTAL_BYTES:
                        result.diagnostics.append({'code': 'file_size_limit', 'file': relative})
                        continue
                    byte_count += len(content)
                    text = content.decode('utf-8-sig')
                    result.texts[relative] = text
                    if path.suffix.lower() == '.py':
                        try:
                            result.trees[relative] = ast.parse(text)
                        except (SyntaxError, ValueError, RecursionError):
                            result.diagnostics.append({'code': 'python_syntax_error', 'file': relative})
                except (OSError, UnicodeError):
                    result.diagnostics.append({'code': 'file_unreadable', 'file': relative})
    except OSError:
        result.diagnostics.append({'code': 'inventory_failed'})
    result.paths.sort()
    return result


def qualified(node, aliases):
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        base = qualified(node.value, aliases)
        return f'{base}.{node.attr}' if base else ''
    return ''


KNOWN = {'flask', 'fastapi', 'django', 'requests', 'httpx', 'ssl', 'sqlite3',
         'psycopg', 'psycopg2', 'pymysql', 'sqlalchemy', 'subprocess', 'os',
         'pickle', 'yaml', 'hashlib', 'random', 'secrets', 'flask_cors'}


def profile_repository(inventory):
    imports = set()
    locations = []
    aliases_by_file = {}
    for file, tree in sorted(inventory.trees.items()):
        aliases = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    aliases[alias.asname or alias.name.split('.')[0]] = (
                        alias.name if alias.asname else alias.name.split('.')[0])
                    name = alias.name.split('.')[0]
                    if name in KNOWN:
                        imports.add(name)
                        locations.append({**evidence(file, 'static_import', node), 'technology': name})
            elif isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    aliases[alias.asname or alias.name] = f'{node.module}.{alias.name}'
                name = node.module.split('.')[0]
                if name in KNOWN:
                    imports.add(name)
                    locations.append({**evidence(file, 'static_import', node), 'technology': name})
        aliases_by_file[file] = aliases
    manifests = sorted(path for path in inventory.paths if manifest(Path(path)))
    languages = ['python'] if inventory.trees or manifests else []
    frameworks = sorted(imports & {'flask', 'fastapi', 'django'})
    profile = {'languages': languages, 'frameworks': frameworks,
               'technologies': sorted(imports), 'dependency_manifests': manifests,
               'evidence': sorted(locations, key=lambda e: (e['file'], e['start_line'], e['technology']))}
    return profile, aliases_by_file
