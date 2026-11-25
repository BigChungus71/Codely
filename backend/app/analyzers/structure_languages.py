"""Language detection, Tree-sitter grammar registry and static repository profiling."""
import json
from pathlib import Path, PurePosixPath
import re

from tree_sitter import Language, Parser
import tree_sitter_java
import tree_sitter_javascript
import tree_sitter_typescript


CODE_EXTENSIONS = {
    '.py': 'python',
    '.java': 'java',
    '.js': 'javascript',
    '.mjs': 'javascript',
    '.cjs': 'javascript',
    '.jsx': 'jsx',
    '.ts': 'typescript',
    '.tsx': 'tsx',
}

IGNORED_MINIFIED_SUFFIXES = ('.min.js', '.bundle.js', '.d.ts')

CONFIG_EXTENSIONS = {
    '.json': 'json',
    '.yaml': 'yaml',
    '.yml': 'yaml',
    '.html': 'html',
    '.htm': 'html',
    '.css': 'css',
    '.scss': 'css',
    '.sql': 'sql',
    '.properties': 'properties',
}

MANIFEST_FILENAMES = {
    'package.json': ('npm', 'nodejs'),
    'package-lock.json': ('npm', 'nodejs'),
    'yarn.lock': ('yarn', 'nodejs'),
    'pnpm-lock.yaml': ('pnpm', 'nodejs'),
    'tsconfig.json': ('typescript', 'typescript'),
    'pom.xml': ('maven', 'java'),
    'build.gradle': ('gradle', 'java'),
    'build.gradle.kts': ('gradle', 'java'),
    'settings.gradle': ('gradle', 'java'),
    'settings.gradle.kts': ('gradle', 'java'),
    'pyproject.toml': ('pip/pep621', 'python'),
    'pipfile': ('pipenv', 'python'),
    'setup.py': ('setuptools', 'python'),
    'setup.cfg': ('setuptools', 'python'),
}

SPRING_CONFIG_FILENAMES = {
    'application.properties',
    'application.yml',
    'application.yaml',
    'bootstrap.properties',
    'bootstrap.yml',
    'bootstrap.yaml',
}

SUPPORTED_CODE_LANGUAGES = frozenset({'python', 'java', 'javascript', 'jsx', 'typescript', 'tsx'})

_TS_LANGUAGES: dict[str, Language] | None = None


def get_ts_language(language: str) -> Language:
    global _TS_LANGUAGES
    if _TS_LANGUAGES is None:
        _TS_LANGUAGES = {
            'java': Language(tree_sitter_java.language()),
            'javascript': Language(tree_sitter_javascript.language()),
            'jsx': Language(tree_sitter_javascript.language()),
            'typescript': Language(tree_sitter_typescript.language_typescript()),
            'tsx': Language(tree_sitter_typescript.language_tsx()),
        }
    return _TS_LANGUAGES[language]


def make_parser(language: str) -> Parser:
    return Parser(get_ts_language(language))


def count_ts_nodes(root_node, limit: int) -> tuple[int, bool]:
    """Iteratively count Tree-sitter AST nodes up to limit+1 without recursion."""
    cursor = root_node.walk()
    count = 0
    reached_parent = False
    while True:
        if not reached_parent:
            count += 1
            if count > limit:
                return count, True
            if cursor.goto_first_child():
                continue
        if cursor.goto_next_sibling():
            reached_parent = False
            continue
        if not cursor.goto_parent():
            break
        reached_parent = True
    return count, False


def classify_file(relative_path: str) -> tuple[str, str | None]:
    """Return (category, kind) where category is code | config | ignored_bundle | unsupported."""
    posix = PurePosixPath(relative_path)
    name_lower = posix.name.lower()
    if any(name_lower.endswith(suffix) for suffix in IGNORED_MINIFIED_SUFFIXES):
        return 'ignored_bundle', None
    ext = posix.suffix.lower()
    if ext in CODE_EXTENSIONS:
        return 'code', CODE_EXTENSIONS[ext]
    if name_lower.startswith('dockerfile'):
        return 'config', 'dockerfile'
    if name_lower.startswith('requirements') and ext == '.txt':
        return 'config', 'manifest'
    if name_lower in MANIFEST_FILENAMES or name_lower in SPRING_CONFIG_FILENAMES:
        return 'config', 'manifest'
    if name_lower.startswith('next.config.'):
        return 'config', 'nextjs_config'
    if ext in CONFIG_EXTENSIONS:
        return 'config', CONFIG_EXTENSIONS[ext]
    return 'unsupported', None


def parse_json_relaxed(text: str) -> dict | None:
    """Parse JSON or JSONC (tsconfig.json with // or /* */ comments) safely."""
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except ValueError:
        pass
    stripped = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    stripped = re.sub(r'(^|[^:])//[^\r\n]*', r'\1', stripped)
    stripped = re.sub(r',(\s*[}\]])', r'\1', stripped)
    try:
        data = json.loads(stripped)
        return data if isinstance(data, dict) else None
    except ValueError:
        return None


def inspect_config_metadata(relative_path: str, text: str) -> dict:
    """Extract non-secret manifest, package-manager and framework profile indicators."""
    name_lower = Path(relative_path).name.lower()
    ext_kind = CONFIG_EXTENSIONS.get(Path(relative_path).suffix.lower())
    info: dict = {
        'file': relative_path,
        'kind': classify_file(relative_path)[1],
        'ext_kind': ext_kind,
        'package_managers': [],
        'frameworks': [],
        'dependencies': [],
        'tsconfig': None,
    }
    if name_lower in MANIFEST_FILENAMES:
        pm, lang = MANIFEST_FILENAMES[name_lower]
        info['package_managers'].append(pm)
        info['language'] = lang
    elif name_lower.startswith('requirements') and name_lower.endswith('.txt'):
        info['package_managers'].append('pip')
        info['language'] = 'python'

    if name_lower == 'package.json':
        data = parse_json_relaxed(text)
        if data:
            deps: set[str] = set()
            for section in ('dependencies', 'devDependencies', 'peerDependencies'):
                block = data.get(section)
                if isinstance(block, dict):
                    deps.update(str(k) for k in block.keys() if isinstance(k, str))
            info['dependencies'] = sorted(deps)
            if 'next' in deps:
                info['frameworks'].append('nextjs')
            if 'react' in deps or 'react-dom' in deps:
                info['frameworks'].append('react')
            if 'express' in deps:
                info['frameworks'].append('express')
            if '@nestjs/core' in deps or '@nestjs/common' in deps:
                info['frameworks'].append('nestjs')
            if 'typescript' in deps:
                info['package_managers'].append('typescript')
    elif name_lower == 'tsconfig.json':
        data = parse_json_relaxed(text)
        if data and isinstance(data.get('compilerOptions'), dict):
            opts = data['compilerOptions']
            paths = opts.get('paths')
            clean_paths = {}
            if isinstance(paths, dict):
                for alias, targets in paths.items():
                    if isinstance(alias, str) and isinstance(targets, list):
                        clean_paths[alias] = [t for t in targets if isinstance(t, str)]
            base_url = opts.get('baseUrl') if isinstance(opts.get('baseUrl'), str) else None
            info['tsconfig'] = {'base_url': base_url, 'paths': clean_paths}
    elif name_lower == 'pom.xml':
        if 'spring-boot' in text:
            info['frameworks'].append('spring_boot')
        if 'spring-webmvc' in text or 'spring-web' in text:
            info['frameworks'].append('spring_mvc')
    elif name_lower in {'build.gradle', 'build.gradle.kts'}:
        if 'org.springframework.boot' in text or 'spring-boot' in text:
            info['frameworks'].append('spring_boot')
        if 'spring-web' in text:
            info['frameworks'].append('spring_mvc')
    elif name_lower in SPRING_CONFIG_FILENAMES:
        info['frameworks'].append('spring_boot')
        info['language'] = 'java'
    elif name_lower.startswith('next.config.'):
        info['frameworks'].append('nextjs')
    return info
