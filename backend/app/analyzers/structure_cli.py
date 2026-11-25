"""JSON CLI for AST structure; scanner/checklist CLI contracts are unchanged."""
import argparse
import json

from .structure_analyzer import StructureOptions, analyze_repository


def main(argv=None):
    parser = argparse.ArgumentParser(description='Static Python repository structure')
    parser.add_argument('project_path')
    parser.add_argument('--max-files', type=int, default=5000)
    parser.add_argument('--max-file-bytes', type=int, default=1024 * 1024)
    parser.add_argument('--max-repository-bytes', type=int, default=50 * 1024 * 1024)
    parser.add_argument('--source-root', action='append', default=[])
    args = parser.parse_args(argv)
    try:
        options = StructureOptions(max_files=args.max_files, max_file_bytes=args.max_file_bytes,
            max_repository_bytes=args.max_repository_bytes, source_roots=tuple(args.source_root))
        result = analyze_repository(args.project_path, options=options)
    except ValueError:
        parser.error('Invalid analysis limits or source roots')
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.status == 'complete' else 2


if __name__ == '__main__':
    raise SystemExit(main())
