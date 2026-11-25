import * as vscode from 'vscode';
import axios from 'axios';

import { indexWorkspace, searchIndex, SearchResult } from './localIndex';
import { CodeRAGDashboard } from './webviewPanel';

// ── Configuration (Local Backend) ──────────────────────────────────────────
const BACKEND_URL = 'http://127.0.0.1:8000'; 

// ── Helper: Call the Python RAG backend ─────────────────────────────────────
async function fetchCodeRAGContext(query: string): Promise<SearchResult> {
    return await searchIndex(globalContext, BACKEND_URL, query);
}

// ── Helper: Architect Feature Handler ───────────────────────────────────────
async function handleArchitectAction(action: string) {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
        vscode.window.showErrorMessage('No active editor found.');
        return;
    }

    let selectedText = editor.document.getText(editor.selection);
    if (!selectedText.trim()) {
        selectedText = editor.document.getText(); // Full document if no selection
    }

    if (!selectedText.trim()) {
        vscode.window.showErrorMessage('No text selected or file is empty.');
        return;
    }

    const dashboard = CodeRAGDashboard.createOrShow(BACKEND_URL);
    
    vscode.window.withProgress({
        location: vscode.ProgressLocation.Notification,
        title: `CodeRAG Architect: Processing request...`,
        cancellable: false
    }, async (progress) => {
        try {
            progress.report({ message: 'Fetching semantic context from workspace...' });
            
            // Extract keywords for search
            const queryKeywords = selectedText.slice(0, 300).replace(/\n/g, ' ');
            const result = await fetchCodeRAGContext(queryKeywords);
            const context_chunks = result.chunks.map(c => c.text);

            progress.report({ message: 'Architect generating insights...' });

            const endpointMap: Record<string, string> = {
                'blast_radius': '/blast-radius',
                'debug': '/debug-error',
                'review': '/review-code'
            };

            const response = await axios.post(`${BACKEND_URL}${endpointMap[action]}`, {
                input_text: selectedText,
                action: action,
                context_chunks: context_chunks
            }, { timeout: 60000 });

            // Post to dashboard
            dashboard.updateArchitectReport(response.data.report_markdown);
            vscode.window.showInformationMessage('CodeRAG Architect: Analysis complete.');
        } catch (error: any) {
            vscode.window.showErrorMessage(`CodeRAG Architect Failed: ${error.message}`);
        }
    });
}

// ── Status Bar Item (always visible branding) ───────────────────────────────
let statusBarItem: vscode.StatusBarItem;
let globalContext: vscode.ExtensionContext;

export function activate(context: vscode.ExtensionContext) {
    globalContext = context;
    console.log('CodeRAG v2.0 activated — Dashboard + Context Visualizer + Confidence Checker ready.');
    vscode.window.showInformationMessage('CodeRAG v2.0 is Active!');

    // ── Status Bar: CodeRAG Branding ────────────────────────────────────────
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.text = '$(database) CodeRAG';
    statusBarItem.tooltip = 'CodeRAG: Semantic Code Intelligence Engine is active';
    statusBarItem.command = 'coderag.openDashboard';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    // ── Command: Open Dashboard ────────────────────────────────────────────
    let dashboardCmd = vscode.commands.registerCommand('coderag.openDashboard', () => {
        CodeRAGDashboard.createOrShow(BACKEND_URL);
    });

    // ── Command: Upload Document ───────────────────────────────────────────
    let uploadDocCmd = vscode.commands.registerCommand('coderag.uploadDoc', async () => {
        const dashboard = CodeRAGDashboard.createOrShow(BACKEND_URL);
        // The dashboard handles the upload UI internally
        vscode.window.showInformationMessage('CodeRAG: Use the Project Memory tab in the Dashboard to upload documents.');
    });

    // ── Commands: Architect Studio ──────────────────────────────────────────
    let blastRadiusCmd = vscode.commands.registerCommand('coderag.analyzeBlastRadius', () => handleArchitectAction('blast_radius'));
    let debugErrorCmd = vscode.commands.registerCommand('coderag.debugError', () => handleArchitectAction('debug'));
    let reviewCodeCmd = vscode.commands.registerCommand('coderag.reviewCode', () => handleArchitectAction('review'));

    // ── Command: Index Workspace ────────────────────────────────────────────
    let indexCmd = vscode.commands.registerCommand('coderag.indexWorkspace', async () => {
        const workspaceFolders = vscode.workspace.workspaceFolders;
        if (!workspaceFolders || workspaceFolders.length === 0) {
            vscode.window.showErrorMessage('No workspace folder open.');
            return;
        }

        statusBarItem.text = '$(loading~spin) CodeRAG: Indexing...';

        vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: "CodeRAG: Indexing workspace locally...",
            cancellable: false
        }, async (progress) => {
            try {
                const chunksIndexed = await indexWorkspace(globalContext, BACKEND_URL, (msg) => {
                    progress.report({ message: msg });
                });
                statusBarItem.text = '$(database) CodeRAG ✓';
                vscode.window.showInformationMessage(
                    `CodeRAG: Local index created with ${chunksIndexed} chunks!`
                );
            } catch (error: any) {
                statusBarItem.text = '$(database) CodeRAG ✗';
                vscode.window.showErrorMessage(`CodeRAG Indexing Failed: ${error.message}`);
            }
        });
    });

    // ── Autonomous Language Model Tool: codeRagSearch ────────────────────────
    console.log('Registering codeRagSearch tool...');
    const coderagTool = vscode.lm.registerTool('codeRagSearch', {
        async invoke(options: vscode.LanguageModelToolInvocationOptions<{ query: string }>, token: vscode.CancellationToken) {
            const query = options.input.query;
            
            vscode.window.showInformationMessage(`CodeRAG: Feeding context to Copilot for: "${query}"`);
            statusBarItem.text = '$(loading~spin) CodeRAG: Searching...';

            try {
                const result = await fetchCodeRAGContext(query);

                statusBarItem.text = `$(database) CodeRAG ✓ (${result.sources.length} files)`;

                // Open and update the dashboard with context data
                const dashboard = CodeRAGDashboard.createOrShow(BACKEND_URL);
                dashboard.updateAll(
                    result.chunks,
                    query,
                    result.retrievalTimeMs,
                    result.confidence
                );

                return new vscode.LanguageModelToolResult([
                    new vscode.LanguageModelTextPart(
                        `### CodeRAG Retrieved Context (${result.sources.length} source files) ###\n\n${result.context}\n\n### Source Files ###\n${result.sources.map(s => `- ${s}`).join('\n')}`
                    )
                ]);
            } catch (error: any) {
                statusBarItem.text = '$(database) CodeRAG';
                return new vscode.LanguageModelToolResult([
                    new vscode.LanguageModelTextPart(`CodeRAG search failed: ${error.message}`)
                ]);
            }
        }
    });

    // ── Chat Participant: @coderag ──────────────────────────────────────────
    const coderagParticipant = vscode.chat.createChatParticipant('coderag', async (request, chatContext, response, token) => {
        const query = request.prompt;

        response.progress('CodeRAG: Retrieving context from semantic engine...');
        statusBarItem.text = '$(loading~spin) CodeRAG: Searching...';

        try {
            const result = await fetchCodeRAGContext(query);

            statusBarItem.text = `$(database) CodeRAG ✓ (${result.sources.length} files)`;
            response.progress(`Retrieved ${result.sources.length} source files. Generating answer...`);

            // Open and update the dashboard
            const dashboard = CodeRAGDashboard.createOrShow(BACKEND_URL);
            dashboard.updateAll(
                result.chunks,
                query,
                result.retrievalTimeMs,
                result.confidence
            );

            // Inject RAG context into Copilot's brain
            const systemPrompt = `You are CodeRAG, an intelligent coding assistant. Answer the user's question using ONLY the following real code retrieved from their repository's semantic vector database. Do NOT invent functions or APIs that aren't shown below.

### RETRIEVED REPOSITORY CODE ###
${result.context}
`;

            const messages = [
                vscode.LanguageModelChatMessage.User(systemPrompt),
                vscode.LanguageModelChatMessage.User(query)
            ];

            const models = await vscode.lm.selectChatModels({ vendor: 'copilot', family: 'gpt-4o' });

            if (!models || models.length === 0) {
                response.markdown('CodeRAG Error: No Copilot models found. Ensure GitHub Copilot Chat is active.');
                return;
            }

            const chatResponse = await models[0].sendRequest(messages, {}, token);

            for await (const fragment of chatResponse.text) {
                response.markdown(fragment);
            }

            // Show CodeRAG branding and sources
            response.markdown('\n\n---\n');
            response.markdown(`**Context provided by CodeRAG Semantic Engine** (${result.chunks.length} chunks, ${result.retrievalTimeMs}ms)\n`);
            result.sources.forEach((s: string) => response.markdown(`- \`${s}\`\n`));

            // Show confidence summary inline
            if (result.confidence) {
                const pct = Math.round(result.confidence.overall_confidence * 100);
                const statusMark = result.confidence.level === 'high' ? '[VERIFIED]' : result.confidence.level === 'medium' ? '[WARNING]' : '[UNVERIFIED]';
                response.markdown(`\n**${statusMark} Confidence: ${pct}%** — ${result.confidence.stats.verified_count} verified, ${result.confidence.stats.warning_count} warnings, ${result.confidence.stats.error_count} errors\n`);
            }

        } catch (error: any) {
            statusBarItem.text = '$(database) CodeRAG';
            response.markdown(`**CodeRAG Error:** ${error.message}`);
        }
    });

    coderagParticipant.iconPath = new vscode.ThemeIcon('database');

    context.subscriptions.push(
        indexCmd, dashboardCmd, uploadDocCmd, 
        blastRadiusCmd, debugErrorCmd, reviewCodeCmd,
        coderagTool, coderagParticipant
    );
}

export function deactivate() {
    if (statusBarItem) {
        statusBarItem.dispose();
    }
}
