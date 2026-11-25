"""Explicit convenience CLI: runs AST structure, graph build and rule evaluation once."""
import argparse
import json

from .architecture_graph import build_architecture_graph
from .architecture_policy import load_policy
from .architecture_rules import evaluate_architecture
from .structure_analyzer import analyze_repository


def main(argv=None):
    parser = argparse.ArgumentParser(description='Deterministic architecture rules and recommendation engine')
    parser.add_argument('project_path')
    parser.add_argument('--policy', help='Optional JSON architecture policy file')
    parser.add_argument(
        '--gemini-package',
        action='store_true',
        help='Output structured Gemini evidence package instead of raw evaluation payload',
    )
    args = parser.parse_args(argv)
    policy = load_policy(args.policy) if args.policy else None
    structure = analyze_repository(args.project_path)
    architecture = build_architecture_graph(structure)
    result = evaluate_architecture(structure, architecture, policy=policy)
    payload = result.gemini_evidence_package() if args.gemini_package else result.to_dict()
    print(json.dumps(payload, indent=2))
    return 0 if result.status == 'complete' else 2


if __name__ == '__main__':
    raise SystemExit(main())
