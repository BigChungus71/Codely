"""Explicit end-to-end convenience CLI; each pipeline stage runs once."""
import argparse
import json

from .semgrep_adapter import scan_repository
from .structure_analyzer import analyze_repository
from .architecture_graph import build_architecture_graph
from .impact_analyzer import analyze_security_impact


def main(argv=None):
    parser = argparse.ArgumentParser(description='Static architectural security impact evidence')
    parser.add_argument('project_path')
    parser.add_argument('--finding-id')
    args = parser.parse_args(argv)
    scan = scan_repository(args.project_path)
    structure = analyze_repository(args.project_path)
    architecture = build_architecture_graph(structure)
    result = analyze_security_impact(scan,structure,architecture,finding_id=args.finding_id)
    print(json.dumps(result.to_dict(),indent=2))
    return 0 if result.status=='complete' else 2


if __name__ == '__main__':
    raise SystemExit(main())
