"""Run Semgrep once, then reuse its result for the reference checklist."""
import argparse
import json
from pathlib import Path

from ..analyzers.semgrep_adapter import scan_repository
from .engine import evaluate_repository


def main(argv=None):
    parser = argparse.ArgumentParser(description='Static versioned Python security checklist')
    parser.add_argument('project_path')
    parser.add_argument('--scan-result', help='Reuse trusted JSON from this repository version; no new scan')
    args = parser.parse_args(argv)
    if args.scan_result:
        path = Path(args.scan_result)
        try:
            if path.stat().st_size > 32 * 1024 * 1024:
                raise ValueError('oversized')
            with path.open('rb') as source:
                payload = source.read(32 * 1024 * 1024 + 1)
            scan = json.loads(payload)
        except (OSError, ValueError):
            parser.error('Cannot read valid bounded scanner JSON')
    else:
        scan = scan_repository(args.project_path)
    result = evaluate_repository(args.project_path, scan)
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.coverage['status'] == 'complete' else 2


if __name__ == '__main__':
    raise SystemExit(main())
