# Codely integration ledger

Base and release branch: `integration/codely-demo` starts from the frontend application. Source refs below are the snapshot fetched for this checkpoint.

| Component | Remote branch | Exact source commit | Integration method | Status |
| --- | --- | --- | --- | --- |
| Original archives | `main` | `0805457b96a2f60e768bd9efbc22e091f3f1d89b` | Inventory only. The extracted backend comes through M2. | Archived baseline |
| Frontend | `feat/frontend-workspace` | `19e9a7b0f69742c646714cadc547782a0344b3e5` | Branch base | Next.js workspace and chat run |
| M2 backend | `feature/backend-core` | `ada47e483e0256c5ca147a3fd6db2f0766028d32` | Cherry-pick `62eb472` plus integration patches | FastAPI API and client |
| M3 scanner | `feature/security-analysis` | `aecdcfe10c199ff8afa89bf5488d8c00394fae0f` | Also an ancestor of the selected `security-analysis` snapshot | Native Python Semgrep verified |
| M3 checklist and structure | `security-analysis` | `ed8c16b49141dd30301b032d4aab0a80f11a5b8d` | Selective import of analyzer, checklist, contracts, fixtures, tools, and tests. Checklist milestone `98b9d8d` included. | AST projection and native checklist tests verified |
| M4 AI | `feature/ai-intelligence` | `9658fe0ff35a02d6e27beede2eba8f67fa6d07ac` | Cherry-pick `2c18d57` plus integration patches | Provider contracts and retrieval tested. Live provider credentials required. |

For the next cycle, fetch and prune, then compare each source tip to its recorded SHA. Merge or cherry-pick only incoming frontend commits after reviewing overlaps. For M2 and M4 inspect commit deltas from the recorded SHA and cherry-pick compatible changes. For M3 check both refs for shared ancestors first, then apply the relevant analyzer, rule, schema, and test deltas once. Update each SHA and method only after verification. Keep integration changes on this branch and retain the UI and API adaptations when reviewing incoming changes.
