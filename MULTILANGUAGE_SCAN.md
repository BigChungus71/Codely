# Java and web scanning handoff

The scanner uses local Semgrep 1.187.0 on a bounded read-only snapshot. Python keeps the existing rule pack and finding shape. The Java and web packs are bundled locally and select Java, TypeScript/TSX, and JavaScript/JSX/CJS/MJS syntax. No remote rule fetching or target execution is needed.

| Pack | Rules |
| --- | --- |
| Java | Concatenated SQL and commands, object streams, legacy digests, XML parser review, permissive hostname verification, disabled Spring CSRF, credential-like literals |
| Web | Dynamic evaluation and function construction, concatenated commands and file paths, raw HTML assignment, disabled TLS verification, credential-like literals, token-like use of Math.random |

A match is a static review lead. Concatenation and naming patterns do not establish data flow. Credential-like literals may be placeholders and XML factory creation does not establish effective parser settings. Finding messages never interpolate matched source values. No cross-file taint, runtime proof, dependency CVEs, or completeness guarantee is provided.

The adapter keeps `complete`, `partial`, and `error` and adds `coverage`. The coverage status distinguishes `unsupported` and `timeout`. The numeric fields reflect discovered files or Semgrep's reported paths. `excluded_files` counts observed files skipped before staging. Descendants of pruned directories are not visited or counted as files. `excluded_directory_count` records pruned directories. `unscanned_supported_files` counts staged files Semgrep did not report scanning. Detected/unsupported entries are limited to recognized source extensions. Mixed-language findings retain stable relative paths, normalized severity, one-based source lines and CWE IDs. The Python checklist uses Python findings and ignores the known Java/web packs.

The FastAPI mapper should forward coverage for successful, partial and failed scans and retain the existing findings fields. A failed or unsupported scan must stay separate from completed zero findings. For impact analysis, scope to Python findings with Python coverage.

Native verification used `CODELY_RUN_SEMGREP_INTEGRATION=1 python -m pytest backend/tests -q`. 344 tests passed on Python 3.12. The Java and TypeScript pairs verified rule IDs, line locations, CWEs, language coverage and no false matches in the paired safe fixtures.

The read-only local VoiceAIAgentPro working checkout completed with 251 files scanned, 82 observed files excluded, 4 directories pruned, and zero staged-but-unscanned files. Java, JavaScript, Python and TypeScript ran. Shell was detected and unsupported. Semgrep returned 23 medium-severity credential-like JavaScript/TypeScript-family literals (CWE-798), with no Java rule matches. These counts describe the local working checkout, including its pre-existing edits and untracked files. Source text and matched values were omitted from the report.
