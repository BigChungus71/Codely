# Multi-Language Security and Code Intelligence

Phase 8 extends Codely's Security and Code Intelligence pipeline from Python-only AST
analysis to **Python, Java, JavaScript, TypeScript, JSX, and TSX**, while recognizing
JSON, YAML, HTML, CSS, SQL, and Dockerfiles for repository profiling and checklist
evaluation. Target source code and package manifests are never executed or installed.

## Supported language and framework matrix

| Language / Format | Parsing / Analysis | Security Rules | Frameworks & Indicators | Dependency Resolution |
| --- | --- | --- | --- | --- |
| Python (`.py`) | Python 3.11 AST (`structure_extractor.py`) | 12 rules (`python-security.yaml`) | FastAPI, Flask, Django, SQLAlchemy, SQLModel | Absolute, relative, `__init__.py`, `src` roots, stdlib/external |
| Java (`.java`) | Tree-sitter (`tree-sitter-java`) | 10 rules (`java-security.yaml`) | Spring Boot, Spring MVC, Spring Security, JPA | Package + class FQN, wildcards, `java.*`/`javax.*`/`jakarta.*`, `src/main/java` |
| JavaScript / JSX (`.js`, `.mjs`, `.cjs`, `.jsx`) | Tree-sitter (`tree-sitter-javascript`) | 12 rules (`web-security.yaml`) | React, Next.js, Express, Node.js, Prisma/Mongoose/Sequelize/TypeORM | Relative `./`/`../`, extensions, `index.*`, `node:`/Node stdlib, `package.json` deps |
| TypeScript / TSX (`.ts`, `.tsx`) | Tree-sitter (`tree-sitter-typescript`) | 12 rules (`web-security.yaml`) | React, Next.js, NestJS, Express, TypeORM/Prisma | Relative, extensions, `index.*`, `tsconfig.json` `paths` + `baseUrl` aliases |
| Config & Profiling (`.json`, `.yaml`/`.yml`, `.html`, `.css`, `.sql`, `Dockerfile*`, `pom.xml`, `build.gradle*`, `package.json`, `requirements*.txt`, `pyproject.toml`) | Safe read-only text/JSON/XML/TOML inspection | Checklist indicators | Spring Boot `application.*`, Next.js config, npm/Maven/Gradle/pip manifests | Declared npm deps & TS path aliases feed static resolver |

## Security rule packs (34 total rules)

Validate all three packs offline using installed Semgrep schemas and native `semgrep-core`:

```powershell
python tools/validate_security_rules.py
```

- **Python (`python-security-v2`, 12 rules)**: `dynamic-eval`, `dynamic-exec`, `sql-injection`, `command-injection`, `hardcoded-credential`, `unsafe-pickle`, `unsafe-yaml`, `weak-password-hash`, `tls-verification-disabled`, `insecure-tempfile`, `flask-debug`, `insecure-security-random`.
- **Java (`java-security-v1`, 10 rules)**: `sql-concatenation`, `command-concatenation`, `object-stream`, `weak-digest`, `xml-factory`, `permissive-hostname-verifier`, `csrf-disabled`, `credential-literal`, `open-redirect`, `insecure-cookie`.
- **Web JS/TS/JSX/TSX (`web-security-v1`, 12 rules)**: `dynamic-eval`, `function-constructor`, `command-concatenation`, `raw-html`, `tls-disabled`, `dynamic-file-path`, `credential-literal`, `security-random`, `sql-concatenation`, `dangerously-set-inner-html`, `insecure-cookie`, `open-redirect`.

All rules include stable IDs, severity, CWE IDs, OWASP 2021 tags, descriptions,
remediation guidance, reference URLs, and paired positive/negative static fixtures.

## Multi-language graph, checklist, ASIM & architecture rules

- **Architecture Graph** (`architecture_graph.py`): Preserves `imports` edges in the
  NetworkX `DiGraph` for cycles, fan-in/fan-out, and traversals, while emitting distinct
  typed semantic edges (`inherits`, `implements`, `references_component`, and inferred
  `potential_api_call`) with `confidence` (`confirmed` vs `inferred`).
- **Checklist Engine** (`backend/app/checklists/`): Preserves the 15-check v1.0.0 schema
  and evaluates Spring Boot (`application.properties`/`application.yml`, `pom.xml`,
  `@CrossOrigin`, `@PreAuthorize`), Node.js/Express (`package.json` + lockfiles,
  `process.env`, `cors()`, cookies), React/Next.js, Docker `USER`, and multi-language
  test indicators (`*Test.java`, `*.test.*`, `*.spec.*`).
- **ASIM** (`impact_analyzer.py`): Maps Python, Java, JavaScript, TypeScript, JSX, and
  TSX findings to exact enclosing classes/methods/functions and traverses observed
  import dependents, while separately listing cross-language `inferred_relationships`
  without claiming confirmed exploit spread.
- **Architecture Rules** (`architecture_rules.py`): Evaluates all 12 structural and
  heuristic rules across Python, Java, JS, TS, JSX, and TSX without forcing a universal
  layered pattern when `policy=None`, and distinguishes `implements` from class
  inheritance depth (`CODELY-ARCH-010`).

## Dependencies

Pinned in `requirements-security.txt`:
- `semgrep==1.187.0`
- `networkx==3.6.1`
- `pytest==9.2.0`
- `tree-sitter==0.27.0`
- `tree-sitter-java==0.23.5`
- `tree-sitter-javascript==0.25.0`
- `tree-sitter-typescript==0.23.2`

## Known limitations

- **Fully supported**: Python AST; Java/JS/JSX/TS/TSX Tree-sitter parsing; static relative/package/`tsconfig.json` path-alias resolution; 34 offline-validated Semgrep patterns; 15 checklist indicators; graph/ASIM/architecture evaluation across these languages.
- **Partially supported**: Wildcard Java imports across multiple classes in one package stay `ambiguous`; dynamic `import()` / `require(variable)`, reflection, Spring DI bean wiring without imports, and unmodeled cross-file taint remain static gaps; `potential_api_call` links match normalized static literal paths only (`inferred`).
- **Unsupported**: Languages outside Python/Java/JS/JSX/TS/TSX (e.g., Go, Rust, C/C++, Ruby, PHP) are counted in `unsupported_languages` / `unsupported_files` and never reported as clean scans; dependency CVE advisory lookup is not performed without an advisory database.
