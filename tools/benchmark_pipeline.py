"""Measure actual end-to-end Codely pipeline timings across representative static fixtures."""
import json
from pathlib import Path
import platform
import sys

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.analyzers.architecture_policy import load_policy
from backend.app.analyzers.pipeline import run_analysis_pipeline


def main() -> None:
    policy = load_policy(ROOT / 'contracts/examples/architecture-policy-v1.json')
    schema = json.loads((ROOT / 'contracts/unified-pipeline-v1.schema.json').read_text(encoding='utf-8'))
    targets = [
        'fixtures/impact_demo',
        'fixtures/spring_boot_demo',
        'fixtures/express_demo',
        'fixtures/fullstack_demo',
        'fixtures/architecture_rules_demo',
    ]
    rows = []
    for target in targets:
        res = run_analysis_pipeline(str(ROOT / target), policy=policy)
        if target == 'fixtures/fullstack_demo':
            payload = res.to_dict()
            jsonschema.Draft202012Validator(schema).validate(payload)
            (ROOT / 'contracts/examples/unified-pipeline-v1.json').write_text(
                json.dumps(payload, indent=2) + '\n',
                encoding='utf-8',
            )
        rows.append(
            {
                'repo': target,
                'status': res.status,
                'files': res.coverage['total_discovered_code_files'],
                'parsed': res.coverage['files_analyzed'],
                'languages': res.profile['languages'],
                'frameworks': res.profile['frameworks'],
                'findings': res.scan.summary['total'],
                'nodes': len(res.architecture.nodes),
                'edges': len(res.architecture.edges),
                'observations': res.architecture_evaluation.summary['total_observations'],
                'timings_ms': res.timings_ms,
            }
        )
    print(json.dumps({'python': sys.version.split()[0], 'platform': platform.platform(), 'results': rows}, indent=2))


if __name__ == '__main__':
    main()
