# Add Codely project browsing and analysis integration APIs

Frontend users can select the actual VoiceAIAgentPro checkout, browse source, and request scanner findings, selected-finding explanations, and architecture graphs through stable `/api/projects` contracts. Analysis adapters validate teammate outputs and return explicit unavailable errors until services are configured. Completed scans are cached only for the same repository content version; partial scans and edits during analysis are rejected.

Existing CodeRAG routes are preserved. Optional vector/AI dependencies load on use, allowing demo startup without them. No VoiceAIAgentPro source was changed. No findings, AI explanations, or graph relationships are invented.

Validation: 12 smoke tests passed. Real checkout projects/tree/source/health returned 200 (296 browsable files); absent scanner and architecture services returned 503. External Gemini and real scanning are not verified. Read DEMO_README.md for service contracts and remaining blockers.

Git provenance: imported ZIP baseline in a new local repository, branch feature/backend-core. This packaged branch uses the BigChungus71/Codely remote; no hosted PR was requested. Run one worker for the in-memory scan cache. Custom adapter hooks must implement their own timeouts.
