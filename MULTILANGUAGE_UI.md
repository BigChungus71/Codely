# Repository scanner and architecture views

Set `NEXT_PUBLIC_CODELY_API_URL` to the Codely FastAPI URL and open `/scanner`. Scan a configured repository to see observed findings, rule and CWE metadata, and measured detected/analyzed/unsupported language coverage. Failed or partial scans have an explicit error and can show partial findings independently of completed zero findings. Click **Open source** to navigate to the recorded line.

Use **Architecture view** to choose **System Architecture** or **Code Dependencies**, then click **Load architecture**. The viewer presents component groups, relationship confidence and evidence, partial warnings, module focus, paged edges, zoom, scrolling and source navigation. Inferred API links are labeled. An unsupported or unavailable provider appears as an error.

The existing uploaded-file workflow remains under **Review uploaded snippets with AI**. It returns suggestions for supplied text and rejects unsupported or invalid output. A GitHub URL alone does not supply source and is no longer accepted. The UI no longer substitutes seeded findings. Repository scanning is always the deterministic FastAPI path.

Integration source revisions are scanner `12c1f548fc5e5ca27d8e47fc808ed761599ce999`, system graph `4fb177cf73fc7e01993932e0872ff40bffc1c574`, and API compatibility `e006ac89b70b5029b3658d437615bff76ef2e7ec`. The integration branch was inspected at `2bf4e688ecfd92a9c7e970c68624433efbc897b3` and left untouched. Apply only the new feature deltas. Reconcile the shared client and scanner component instead of replacing the integration versions, so the existing static impact, cached findings, explanation and design-chat behavior remain. Preserve the existing Python dependency hook and add the system hook. Install the optional parser requirements alongside the pinned scanner requirements.

Verification passed `npm run typecheck`, `npm run build`, and five client tests. Chrome against the independent feature-branch API exercised all four scanned languages, real findings and CWE metadata, finding source navigation, both architecture views, zoom and opening relationship evidence.
