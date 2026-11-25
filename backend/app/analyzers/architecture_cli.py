"""Convenience CLI: parse structure once, then build the pure graph."""
import argparse
import json

from .structure_analyzer import analyze_repository
from .architecture_graph import build_architecture_graph


def main(argv=None):
    parser = argparse.ArgumentParser(description='Observed Python import architecture graph')
    parser.add_argument('project_path')
    args = parser.parse_args(argv)
    structure = analyze_repository(args.project_path)
    architecture = build_architecture_graph(structure)
    print(json.dumps(architecture.to_dict(), indent=2))
    return 0 if architecture.status == 'complete' else 2


if __name__ == '__main__':
    raise SystemExit(main())
