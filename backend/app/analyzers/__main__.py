"""Command-line entry point for the deterministic security pipeline."""
import argparse
import json

from .semgrep_adapter import scan_repository


def main():
    parser = argparse.ArgumentParser(description='Scan Python source with trusted local rules')
    parser.add_argument('project_path')
    args = parser.parse_args()
    result = scan_repository(args.project_path)
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.status == 'complete' else 2


if __name__ == '__main__':
    raise SystemExit(main())
