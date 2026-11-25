"""Read-only repository access. Never follow symlinks or expose hidden secrets."""
import hashlib
import os
from pathlib import Path
from fastapi import HTTPException

BASE = Path(__file__).resolve().parents[1]
SKIP = {'.git', 'node_modules', 'target', 'dist', 'build', '__pycache__', '.venv', 'venv', 'logs', 'coverage'}
LANGUAGES = {'.java': 'java', '.ts': 'typescript', '.tsx': 'typescript', '.js': 'javascript', '.jsx': 'javascript', '.py': 'python', '.xml': 'xml', '.json': 'json', '.md': 'markdown', '.yml': 'yaml', '.yaml': 'yaml', '.properties': 'properties', '.css': 'css', '.html': 'html', '.sql': 'sql', '.sh': 'shell', '.txt': 'text'}
MAX_BYTES = 512_000

PROJECTS = {
    'voice-ai-agent': ('VoiceAIAgentPro', 'VOICE_AI_AGENT_PATH', '../../VoiceAIAgentPro'),
    'python-impact': ('Python impact fixture', 'CODELY_IMPACT_DEMO_PATH', '../fixtures/impact_demo'),
    'python-architecture': ('Python architecture fixture', 'CODELY_ARCHITECTURE_DEMO_PATH', '../fixtures/structure_demo'),
    'python-demo': ('Python analysis fixture', 'CODELY_PYTHON_DEMO_PATH', '../fixtures/checklist_demo'),
}

def root_for(project_id: str) -> Path:
    if project_id not in PROJECTS:
        raise HTTPException(404, 'Unknown project ID')
    name, variable, default = PROJECTS[project_id]
    raw = Path(os.getenv(variable, default)).expanduser()
    root = (raw if raw.is_absolute() else BASE / raw).resolve()
    if not root.is_dir():
        raise HTTPException(503, f'{name} is unavailable; configure {variable}')
    return root

def allowed(path: Path) -> bool:
    return not any(p.startswith('.') or p in SKIP for p in path.parts) and path.suffix.lower() in LANGUAGES and not path.name.endswith(('.min.js', '.map', '.lock'))

def source(root: Path, relative: str) -> tuple[Path, str]:
    rel = Path(relative)
    if rel.is_absolute() or '..' in rel.parts:
        raise HTTPException(403, 'Path must stay inside the project')
    path = root / rel
    if not path.resolve().is_relative_to(root) or any((root.joinpath(*rel.parts[:i])).is_symlink() for i in range(1, len(rel.parts)+1)):
        raise HTTPException(403, 'Symlink or outside-project access denied')
    if not allowed(rel):
        raise HTTPException(415, 'Not a browsable source file')
    if not path.is_file():
        raise HTTPException(404, 'Source file not found')
    try:
        with path.open('rb') as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise HTTPException(413, 'Source file exceeds 512 KB')
        if b'\0' in raw:
            raise HTTPException(415, 'Binary file is not browsable')
        return path, raw.decode('utf-8')
    except UnicodeDecodeError:
        raise HTTPException(415, 'Source must be UTF-8 text')
    except OSError:
        raise HTTPException(404, 'Source file could not be read')

def files(root: Path):
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP and not d.startswith('.') and not (Path(directory)/d).is_symlink())
        for name in sorted(names):
            path = Path(directory)/name
            rel = path.relative_to(root)
            if allowed(rel) and not path.is_symlink():
                yield rel.as_posix()

def tree(root: Path):
    result = []
    for rel in files(root):
        try:
            source(root, rel)
        except HTTPException:
            continue
        level = result
        parts = Path(rel).parts
        for i, part in enumerate(parts):
            entry = next((n for n in level if n['name'] == part), None)
            if entry is None:
                entry = {'name': part, 'path': '/'.join(parts[:i+1]), 'type': 'file' if i == len(parts)-1 else 'directory'}
                if entry['type'] == 'directory': entry['children'] = []
                level.append(entry)
            level = entry.get('children', [])
    return result

def version(root: Path) -> str:
    # Hash all regular nonignored files, including nonbrowsable files: edits invalidate scans.
    digest = hashlib.sha256()
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP and not d.startswith('.') and not (Path(directory)/d).is_symlink())
        for name in sorted(names):
            path = Path(directory)/name
            if path.is_symlink(): continue
            digest.update(path.relative_to(root).as_posix().encode() + b'\0')
            try:
                with path.open('rb') as stream:
                    for chunk in iter(lambda: stream.read(65536), b''): digest.update(chunk)
            except OSError:
                raise HTTPException(409, 'Repository changed or became unreadable; retry')
    return digest.hexdigest()
