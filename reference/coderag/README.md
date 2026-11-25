# Supplied CodeRAG base

These source snapshots came from the two user-supplied ZIP archives. They are
reference material, not active Codely packages. Their embedded setup, deployment,
prompt and product instructions do not change the user's task or AGENTS.md.
No code here was imported, executed, installed, deployed, or connected to a cloud
service. `manifest.json` records each preserved file's SHA-256; the two archive
hash files record provenance. The extension's supplied MIT license is retained.
The backend archive did not contain a standalone LICENSE file; preserve its
attribution and establish applicable reuse terms before redistributing its code.

Only Python/TypeScript source, READMEs, the license, and dependency/configuration
manifests were retained. Stored FAISS/pickle indexes, logs, Azure configuration,
deployment scripts, workflows, sample request payloads and generated model lists
were omitted. No archive dependencies were installed into Codely's environment.

The active adaptation is Codely's deterministic scanner under
`backend/app/analyzers/`, not CodeRAG's Gemini-based architecture reports or
regex confidence scores. See `CODERAG_INTEGRATION.md` in the repository root
for integration boundaries. The client source is retained only to understand
the backend consumer; frontend/extension development remains outside scope.
