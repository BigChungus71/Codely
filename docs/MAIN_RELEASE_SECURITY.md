# Main release security verification

The release combines the verified integration baseline with current security, Java/React architecture, backend compatibility and frontend updates. It retains static impact, repository chat and Python dependencies. It keeps the BoardUI notice and disables the inherited action that automatically closed pull requests. The separate legacy AI upload/URL review is outside the main release. Repository findings come from native Semgrep.

## Security fixes

- Updated Next.js from 16.3.3 to 16.4.6. The npm advisory audit reports zero known vulnerabilities in the resulting lockfile.
- Legacy CodeRAG routes default to disabled. Explicit opt-in requires a bearer token. Index metadata is JSON and no longer deserializes pickle. Regenerate legacy metadata from trusted source.
- The default API policy accepts loopback hosts and configured local browser origins. Next chat rejects unsolicited browser origins. Maven analysis uses a hardened XML parser.
- The web runtime and the Semgrep subprocess are installed separately. The scanner operates on a bounded local snapshot with bundled rules, passes a restricted environment, and does not start Semgrep's MCP server.

## Verification and outstanding issues

- The VoiceAIAgentPro checkout scan completed with 251 files scanned and 23 medium credential-like web findings. These are static review leads in a separate project. No matched values were exported and the checkout was not edited.
- The Python checklist reported 3 pass, 4 needs review, 8 not applicable, and zero fail. Evaluation of the Python architecture subset reported zero observations across three modules. The separate Java/React system graph returned partial coverage with 50 nodes and 140 relationships.
- Chrome verified a native scan, coverage, finding references, both architecture views, zoom and graph evidence navigation. Frontend typecheck, production build and all five client tests passed.
- Bandit reported no high or medium findings after fixes. Five low flags corresponded to bounded subprocess calls/imports and a checklist classification label.
- The web runtime's dependency scan passed. The separate Semgrep 1.187.0 tool environment has eight published advisories affecting its pinned `mcp`, `opentelemetry-api` and `wcmatch` dependencies. No newer compatible Semgrep release was available during this check. The advisories remain open and isolation does not patch them. Keep the scanner in the local demo workflow and reassess when upstream releases an update.

Offline schema and native compilation validated all 28 bundled rules. The full split-runtime Python suite passed 426 tests and 38 subtests. A credential-pattern check found no matches in tracked text or text entries of the original archives.
