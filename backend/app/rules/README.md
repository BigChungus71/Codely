# Trusted Python security rule pack v2

`python-security.yaml` is the only production pack. Rule IDs below have the
prefix `codely.python.`. Messages contain no interpolated code or credential
values. Every rule has a title, description, Semgrep severity, normalized
severity, CWE, OWASP review tags where applicable, remediation and primary
reference URL in its metadata. This catalog is descriptive; the YAML is what
the scanner executes. `compatibility-smoke.yaml` is a separate legacy probe.

| ID suffix | Severity / CWE | Supported detection and safe example |
| --- | --- | --- |
| `dynamic-eval` | MEDIUM / CWE-95 | `eval(...)`; use a constrained literal parser or explicit dispatch |
| `dynamic-exec` | HIGH / CWE-95 | `exec(...)`; replace dynamically executed statements with explicit functions |
| `sql-injection` | HIGH / CWE-89 | Supported input reaches the first argument of `.execute`/`.executemany`; constant SQL with bound values is the safe alternative |
| `command-injection` | HIGH / CWE-78 | Supported input reaches `os.system`, `os.popen`, or supported subprocess calls with `shell=True`; fixed executable/argument list and `shell=False` is the safe alternative |
| `hardcoded-credential` | HIGH / CWE-798 | Nonempty string literals assigned to credential-like variable/attribute/dict-key names; environment/secret-store lookup is the safe alternative |
| `unsafe-pickle` | HIGH / CWE-502 | Supported input reaches `pickle.load`/`pickle.loads`; use a data-only parser for untrusted content |
| `unsafe-yaml` | HIGH / CWE-502 | Explicit unsafe PyYAML loaders, `unsafe_load`/`unsafe_load_all`, or legacy default `load`/`load_all`; `safe_load` or explicit `SafeLoader` is the safe alternative |
| `weak-password-hash` | HIGH / CWE-916 | Password-named arguments passed directly or via `.encode()` to hashlib MD5/SHA-1/SHA-2 constructors; use a salted password KDF |
| `tls-verification-disabled` | HIGH / CWE-295 | `verify=False` on supported requests/httpx functions and httpx clients, or `ssl._create_unverified_context`; use verification and a trusted CA |
| `insecure-tempfile` | MEDIUM / CWE-377 | `tempfile.mktemp`; use an API that creates the file atomically |
| `flask-debug` | HIGH / CWE-489 | Same-scope Flask construction with `.run(debug=True)` or `config["DEBUG"] = True`, or inline Flask construction/run; disable the debugger in deployed applications |
| `insecure-security-random` | MEDIUM / CWE-338 | `random` output flows into a security-named assignment; use `secrets` for security values |

SQL, shell and pickle rules use taint tracking. Their sources are `input`,
Flask request `args`/`form` lookups, `values.get`, `get_json`, `get_data`, and
`data`. Local assignments, interpolation and supported propagation are tracked
within the OSS engine's analysis scope. SQL checks focus on the query argument,
not separately bound parameters. Subprocess sinks are `run`, `call`,
`check_call`, `check_output` and `Popen` with explicit `shell=True`.

The randomness rule also uses taint tracking: supported source functions are
`random`, `randint`, `randrange`, `choice`, `choices`, `getrandbits`, `randbytes`.
Destination names end with or contain underscore-separated token, secret, OTP,
nonce, password, reset_code, session_id or api_key roles. Ordinary simulation
randomness and `secrets` calls are not flagged by this rule.

Credential names include password/passwd/pwd, secret, api_key, access_token,
auth_token, client_secret and secret_key, with optional prefixes. Empty strings
and a narrow set of obvious placeholders are excluded. Short literals such as
`"admin"` remain findings. All committed fixture credentials are synthetic.

OWASP tags are explicitly pinned to the **2021 edition**, not represented as
the latest edition or as comprehensive compliance coverage. They are review
categories: injection (A03), cryptographic failures (A02), authentication
failures (A07), data integrity (A08), and security misconfiguration (A05).
Temporary-file creation has an empty OWASP tag list rather than an invented
mapping. The [OWASP 2021 category index](https://top10.owasp.org/2021/) is the
edition reference. Taint syntax follows the
[Semgrep taint overview](https://docs.semgrep.dev/writing-rules/data-flow/taint-mode/overview).

## Coverage limits

- These rules identify supported risky constructs, not exploitability. Constant
  `eval`/`exec` calls are review findings too. Shadowed builtins or API objects
  with familiar names can produce false positives.
- OSS taint analysis here does not establish cross-file or general cross-function
  data flow. Arbitrary function parameters, Django/FastAPI inputs, uploaded file
  streams, custom request wrappers and additional serializers are not modeled.
  A pickle call outside the modeled sources can remain dangerous but unreported.
- SQL sinks use method names rather than inferred DB driver types. A non-SQL
  object's tainted `.execute` can be a false positive. No SQL dialect or database
  behavior is executed. No general argument-injection detection is claimed for
  `shell=False`.
- A single literal credential name/value heuristic cannot identify all real
  secrets. Dynamically constructed values and unlisted names can be missed;
  synthetic/default settings may need review. No credentials are validated online.
- The hash rule recognizes password-like input names and direct constructor
  usage, not every password storage implementation or KDF parameter policy.
  Randomness context uses assignment names and can miss returns/custom RNGs.
- SafeLoader is treated as the safe YAML alternative. Custom safe loaders,
  aliases, application-specific sanitizers and indirect configuration may not be
  resolved. Default-loader warnings also cover legacy PyYAML behavior; recent
  versions may instead reject calls without a Loader.
- HTTP session mutation, indirect TLS flags, arbitrary wrappers and all Flask
  deployment/environment configurations are not covered. No deployment state
  or reachability is inferred from a debug setting.

## Validation and fixtures

`fixtures/security_rules/expectations.json` is a hand-authored expectation map
for static fixture text. It specifies the exact file, rule ID and source line;
the tests compare all actual findings against it. Fixtures are syntax-parsed
and scanned as data, never imported or executed. There are 37 Python fixtures,
25 expected findings, and a safe counterpart for every rule.

Run offline schema/core validation in a normal Windows PowerShell process:

```powershell
.\.venv\Scripts\python.exe tools\validate_security_rules.py
```

This validates against the installed Semgrep JSON schema and invokes its native
core parser with a local minimal metacheck. It does not run the registry's
community lint pack. Semgrep 1.187.0's CLI `--validate` fetches registry
metachecks, so it is deliberately not used for offline validation. Actual
fixture scans additionally compile and execute the complete local rule pack.
