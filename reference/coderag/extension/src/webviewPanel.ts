/**
 * CodeRAG Intelligence Dashboard — Premium Minimalist Webview Panel
 * ================================================================
 * A high-end, monochrome-focused, professional architectural design
 * with minimal animations and scalable vector graphics (SVGs).
 */

import * as vscode from 'vscode';
import axios from 'axios';

interface ChunkDetail {
    file: string;
    start_line: number;
    text: string;
    score: number;
    source_type: string;
}

interface ConfidenceReport {
    overall_confidence: number;
    level: string;
    verified: { symbol: string; type: string }[];
    warnings: { symbol: string; type: string; reason: string }[];
    errors: { symbol: string; type: string; reason: string }[];
    stats: { total_symbols: number; verified_count: number; warning_count: number; error_count: number };
}

interface DocInfo {
    doc_id: string;
    name: string;
    chunk_count: number;
    uploaded_at: number;
}

// Minimalist SVGs
const ICONS = {
    search: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>`,
    file: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>`,
    doc: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>`,
    shield: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>`,
    check: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>`,
    warn: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>`,
    error: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>`,
    upload: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>`,
    database: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"></ellipse><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"></path><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"></path></svg>`,
    refresh: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>`,
    trash: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>`,
    clock: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>`,
    box: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>`
};

export class CodeRAGDashboard {
    public static currentPanel: CodeRAGDashboard | undefined;
    private readonly _panel: vscode.WebviewPanel;
    private _disposables: vscode.Disposable[] = [];
    private _backendUrl: string;

    private _lastChunks: ChunkDetail[] = [];
    private _lastConfidence: ConfidenceReport | null = null;
    private _lastQuery: string = '';
    private _lastRetrievalTime: number = 0;
    private _lastArchitectReport: string = '';

    private constructor(panel: vscode.WebviewPanel, backendUrl: string) {
        this._panel = panel;
        this._backendUrl = backendUrl;

        this._panel.onDidDispose(() => this.dispose(), null, this._disposables);

        this._panel.webview.onDidReceiveMessage(
            async (message) => {
                switch (message.command) {
                    case 'uploadDoc':
                        await this._handleDocUpload();
                        break;
                    case 'refreshMemory':
                        await this._refreshMemory();
                        break;
                    case 'clearMemory':
                        await this._clearMemory();
                        break;
                    case 'deleteDoc':
                        await this._deleteDoc(message.docId);
                        break;
                }
            },
            null,
            this._disposables
        );

        this._updateWebview();
    }

    public static createOrShow(backendUrl: string) {
        const column = vscode.ViewColumn.Beside;

        if (CodeRAGDashboard.currentPanel) {
            CodeRAGDashboard.currentPanel._panel.reveal(column);
            return CodeRAGDashboard.currentPanel;
        }

        const panel = vscode.window.createWebviewPanel(
            'coderagDashboard',
            'CodeRAG Dashboard',
            column,
            {
                enableScripts: true,
                retainContextWhenHidden: true,
            }
        );

        CodeRAGDashboard.currentPanel = new CodeRAGDashboard(panel, backendUrl);
        return CodeRAGDashboard.currentPanel;
    }

    public updateContext(chunks: ChunkDetail[], query: string, retrievalTimeMs: number) {
        this._lastChunks = chunks;
        this._lastQuery = query;
        this._lastRetrievalTime = retrievalTimeMs;
        this._updateWebview();
        this._panel.webview.postMessage({ command: 'switchTab', tab: 'context' });
    }

    public updateConfidence(report: ConfidenceReport) {
        this._lastConfidence = report;
        this._updateWebview();
        this._panel.webview.postMessage({ command: 'switchTab', tab: 'confidence' });
    }

    public updateArchitectReport(report: string) {
        this._lastArchitectReport = report;
        this._updateWebview();
        this._panel.webview.postMessage({ command: 'switchTab', tab: 'architect' });
    }

    public updateAll(chunks: ChunkDetail[], query: string, retrievalTimeMs: number, confidence: ConfidenceReport) {
        this._lastChunks = chunks;
        this._lastQuery = query;
        this._lastRetrievalTime = retrievalTimeMs;
        this._lastConfidence = confidence;
        this._updateWebview();
    }

    private async _handleDocUpload() {
        const fileUris = await vscode.window.showOpenDialog({
            canSelectMany: false,
            filters: {
                'Documents': ['pdf', 'md', 'txt', 'rst', 'json', 'yaml', 'yml'],
                'All Files': ['*']
            },
            title: 'Upload Document to CodeRAG'
        });

        if (!fileUris || fileUris.length === 0) return;

        const fileUri = fileUris[0];
        const fileBytes = await vscode.workspace.fs.readFile(fileUri);
        const fileName = fileUri.path.split('/').pop() || 'document';

        try {
            const FormData = require('form-data');
            const formData = new FormData();
            formData.append('file', Buffer.from(fileBytes), { filename: fileName });

            const response = await axios.post(`${this._backendUrl}/upload-doc`, formData, {
                headers: formData.getHeaders(),
                timeout: 60000
            });

            vscode.window.showInformationMessage(
                `CodeRAG: ${fileName} uploaded (${response.data.chunk_count} chunks indexed)`
            );
            await this._refreshMemory();
        } catch (err: any) {
            vscode.window.showErrorMessage(`CodeRAG Upload Failed: ${err.message}`);
        }
    }

    private async _refreshMemory() {
        try {
            const [memRes, docRes] = await Promise.all([
                axios.get(`${this._backendUrl}/memory?limit=20`, { timeout: 10000 }),
                axios.get(`${this._backendUrl}/documents`, { timeout: 10000 })
            ]);
            this._panel.webview.postMessage({
                type: 'memoryUpdate',
                history: memRes.data.history,
                documents: docRes.data.documents
            });
        } catch (err) {
            console.error('[CodeRAG Dashboard] Memory refresh failed:', err);
        }
    }

    private async _clearMemory() {
        try {
            await axios.post(`${this._backendUrl}/memory/clear`, {}, { timeout: 10000 });
            vscode.window.showInformationMessage('CodeRAG: Project memory cleared.');
            await this._refreshMemory();
        } catch (err: any) {
            vscode.window.showErrorMessage(`CodeRAG: Failed to clear memory: ${err.message}`);
        }
    }

    private async _deleteDoc(docId: string) {
        try {
            await axios.delete(`${this._backendUrl}/documents/${docId}`, { timeout: 10000 });
            vscode.window.showInformationMessage('CodeRAG: Document removed.');
            await this._refreshMemory();
        } catch (err: any) {
            vscode.window.showErrorMessage(`CodeRAG: Failed to delete document: ${err.message}`);
        }
    }

    private _updateWebview() {
        this._panel.webview.html = this._getHtmlContent();
        this._refreshMemory();
    }

    private _escapeHtml(str: string): string {
        return str
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    private _getChunksHtml(): string {
        if (this._lastChunks.length === 0) {
            return `
                <div class="empty-state">
                    <div class="empty-icon">${ICONS.search}</div>
                    <h3 class="mb-2">Awaiting Query</h3>
                    <p class="text-sm color-muted">Submit a query to CodeRAG to initiate semantic retrieval.</p>
                </div>
            `;
        }

        const statsHtml = `
            <div class="stats-panel mb-4">
                <div class="stat-group">
                    <div class="stat-item">
                        <span class="stat-value">${this._lastChunks.length}</span>
                        <span class="stat-label">CHUNKS</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-value">${new Set(this._lastChunks.map(c => c.file)).size}</span>
                        <span class="stat-label">FILES</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-value">${this._lastRetrievalTime}ms</span>
                        <span class="stat-label">LATENCY</span>
                    </div>
                </div>
                <div class="query-box">
                    <span class="query-prompt">QUERY</span>
                    <span class="query-text">${this._escapeHtml(this._lastQuery)}</span>
                </div>
            </div>
        `;

        const chunksHtml = this._lastChunks.map((chunk) => {
            const scorePercent = Math.round(chunk.score * 100);
            const isHigh = scorePercent >= 60;
            const scoreClass = isHigh ? 'score-high' : 'score-low';
            const icon = chunk.source_type === 'document' ? ICONS.doc : ICONS.file;
            const fileName = chunk.file.split(/[/\\]/).pop() || chunk.file;

            return `
                <div class="card">
                    <div class="card-header flex justify-between align-center">
                        <div class="flex align-center gap-2">
                            <span class="color-muted flex align-center">${icon}</span>
                            <span class="fw-500">${this._escapeHtml(fileName)}</span>
                            ${chunk.source_type === 'document' ? '<span class="badge">DOC</span>' : ''}
                            ${chunk.start_line > 0 ? `<span class="text-xs color-muted">L${chunk.start_line}</span>` : ''}
                        </div>
                        <div class="font-mono text-sm ${scoreClass}">${scorePercent}%</div>
                    </div>
                    <div class="progress-bar mb-2">
                        <div class="progress-fill ${scoreClass}-bg" style="width: ${scorePercent}%"></div>
                    </div>
                    <div class="text-xs color-muted font-mono truncate mb-3">${this._escapeHtml(chunk.file)}</div>
                    <details class="code-details">
                        <summary class="text-xs">VIEW SOURCE CODE</summary>
                        <pre class="code-block font-mono text-xs"><code>${this._escapeHtml(chunk.text)}</code></pre>
                    </details>
                </div>
            `;
        }).join('');

        return statsHtml + '<div class="grid gap-3">' + chunksHtml + '</div>';
    }

    private _getConfidenceHtml(): string {
        if (!this._lastConfidence) {
            return `
                <div class="empty-state">
                    <div class="empty-icon">${ICONS.shield}</div>
                    <h3 class="mb-2">Validation Pending</h3>
                    <p class="text-sm color-muted">Code generation required to perform hallucination checks.</p>
                </div>
            `;
        }

        const c = this._lastConfidence;
        const pct = Math.round(c.overall_confidence * 100);
        const levelLabel = c.level.toUpperCase();
        const levelClass = c.level === 'high' ? 'status-ok' : c.level === 'medium' ? 'status-warn' : 'status-err';
        const levelIcon = c.level === 'high' ? ICONS.check : c.level === 'medium' ? ICONS.warn : ICONS.error;

        const renderBadges = (items: any[], typeClass: string, icon: string) => {
            return items.map(i => `
                <div class="symbol-badge ${typeClass}">
                    <span class="flex align-center">${icon}</span>
                    <span class="font-mono">${this._escapeHtml(i.symbol)}</span>
                    <span class="text-xs opacity-50 ml-auto">${i.type}</span>
                    ${i.reason ? `<div class="w-full text-xs opacity-70 mt-1">${this._escapeHtml(i.reason)}</div>` : ''}
                </div>
            `).join('');
        };

        return `
            <div class="confidence-overview flex flex-col align-center py-6 mb-6">
                <div class="text-4xl font-mono fw-200 mb-2 ${levelClass}-text">${pct}%</div>
                <div class="flex align-center gap-2 tracking-widest text-xs uppercase mb-4 ${levelClass}-text">
                    ${levelIcon} ${levelLabel} CONFIDENCE
                </div>
                <div class="flex gap-4 text-xs font-mono color-muted">
                    <span>VERIFIED:${c.stats.verified_count}</span>
                    <span>WARN:${c.stats.warning_count}</span>
                    <span>ERR:${c.stats.error_count}</span>
                </div>
            </div>

            ${c.errors.length > 0 ? `
                <div class="mb-6">
                    <h4 class="text-xs tracking-widest uppercase color-muted mb-3 border-b pb-2">Unresolved References</h4>
                    <div class="grid gap-2">${renderBadges(c.errors, 'badge-err', ICONS.error)}</div>
                </div>
            ` : ''}

            ${c.warnings.length > 0 ? `
                <div class="mb-6">
                    <h4 class="text-xs tracking-widest uppercase color-muted mb-3 border-b pb-2">Warnings</h4>
                    <div class="grid gap-2">${renderBadges(c.warnings, 'badge-warn', ICONS.warn)}</div>
                </div>
            ` : ''}

            ${c.verified.length > 0 ? `
                <div class="mb-6">
                    <h4 class="text-xs tracking-widest uppercase color-muted mb-3 border-b pb-2">Verified Symbols</h4>
                    <div class="flex flex-wrap gap-2">${renderBadges(c.verified, 'badge-ok', ICONS.check)}</div>
                </div>
            ` : ''}
        `;
    }

    private _getArchitectHtml(): string {
        if (!this._lastArchitectReport) {
            return `
                <div class="empty-state">
                    <div class="empty-icon">${ICONS.box}</div>
                    <h3 class="mb-2">Architect Studio</h3>
                    <p class="text-sm color-muted">Right-click code in your editor to predict semantic blast radius, debug error traces, or review against repository conventions.</p>
                </div>
            `;
        }

        // Simple markdown parser
        let htmlReport = this._escapeHtml(this._lastArchitectReport);
        htmlReport = htmlReport.replace(/^### (.*$)/gim, '<h3 class="mt-4 mb-2 text-base color-high tracking-widest uppercase border-b pb-2">$1</h3>');
        htmlReport = htmlReport.replace(/^## (.*$)/gim, '<h2 class="mt-4 mb-2 text-base color-high tracking-widest uppercase border-b pb-2">$1</h2>');
        htmlReport = htmlReport.replace(/^\# (.*$)/gim, '<h1 class="mt-4 mb-3 text-base color-high tracking-widest uppercase border-b pb-2">$1</h1>');
        htmlReport = htmlReport.replace(/\*\*(.*?)\*\*/gim, '<strong class="color-high fw-600">$1</strong>');
        htmlReport = htmlReport.replace(/\*(.*?)\*/gim, '<em>$1</em>');
        htmlReport = htmlReport.replace(/`(.*?)`/gim, '<code class="badge font-mono text-xs bg-surface">$1</code>');
        htmlReport = htmlReport.replace(/\n\n/gim, '<br><br>');

        return `
            <div class="mb-6">
                <div class="text-xs tracking-widest uppercase color-muted border-b pb-2 mb-4">CodeRAG AI Architect Report</div>
                <div class="card font-sans text-sm color-muted" style="line-height: 1.6;">
                    ${htmlReport}
                </div>
            </div>
        `;
    }

    private _getHtmlContent(): string {
        return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CodeRAG Dashboard</title>
<style>
/* ═══════════════════════════════════════════════════════════════
   Minimalist Monochrome API Dashboard Style
   ═══════════════════════════════════════════════════════════════ */
:root {
    --bg-main: #0a0a0a;
    --bg-surface: #121212;
    --bg-hover: #1a1a1a;
    --border-color: #2a2a2a;
    --text-main: #e0e0e0;
    --text-muted: #888888;
    --accent: #ffffff;
    
    --color-high: #ffffff;
    --color-low: #888888;
    
    --status-err: #ff5555;
    --status-warn: #f1fa8c;
    --status-ok: #50fa7b;

    --font-sans: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', sans-serif;
    --font-mono: 'JetBrains Mono', 'Fira Code', 'SF Mono', monospace;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    background-color: var(--bg-main);
    color: var(--text-main);
    font-family: var(--font-sans);
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
    padding: 0;
}

/* Base Utilities */
.flex { display: flex; }
.flex-col { display: flex; flex-direction: column; }
.justify-between { justify-content: space-between; }
.justify-center { justify-content: center; }
.align-center { align-items: center; }
.gap-2 { gap: 8px; }
.gap-3 { gap: 12px; }
.gap-4 { gap: 16px; }
.grid { display: grid; }
.w-full { width: 100%; }

.text-xs { font-size: 11px; }
.text-sm { font-size: 12px; }
.text-base { font-size: 14px; }
.text-4xl { font-size: 48px; }

.fw-200 { font-weight: 200; }
.fw-400 { font-weight: 400; }
.fw-500 { font-weight: 500; }
.fw-600 { font-weight: 600; }

.font-mono { font-family: var(--font-mono); }
.uppercase { text-transform: uppercase; }
.tracking-widest { letter-spacing: 0.1em; }
.truncate { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.mt-1 { margin-top: 4px; }
.mb-2 { margin-bottom: 8px; }
.mb-3 { margin-bottom: 12px; }
.mb-4 { margin-bottom: 16px; }
.mb-6 { margin-bottom: 24px; }
.py-6 { padding-top: 24px; padding-bottom: 24px; }
.pb-2 { padding-bottom: 8px; }
.ml-auto { margin-left: auto; }

.color-muted { color: var(--text-muted); }
.opacity-50 { opacity: 0.5; }
.opacity-70 { opacity: 0.7; }
.border-b { border-bottom: 1px solid var(--border-color); }

.status-err-text { color: var(--status-err); }
.status-warn-text { color: var(--status-warn); }
.status-ok-text { color: var(--status-ok); }

/* Layout Structure */
.header {
    border-bottom: 1px solid var(--border-color);
    padding: 24px 32px 0;
    position: sticky;
    top: 0;
    background: var(--bg-main);
    z-index: 10;
}

.header-title {
    font-size: 14px;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 20px;
}

.nav-tabs {
    display: flex;
    gap: 24px;
}

.tab {
    background: transparent;
    border: none;
    color: var(--text-muted);
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    padding: 8px 0;
    cursor: pointer;
    border-bottom: 2px solid transparent;
    display: flex;
    align-items: center;
    gap: 6px;
}

.tab:hover { color: var(--text-main); }
.tab.active {
    color: var(--accent);
    border-bottom-color: var(--accent);
}

.content-area {
    padding: 24px 32px;
}

.tab-pane { display: none; }
.tab-pane.active { display: block; }

/* Components */
.card {
    background: var(--bg-surface);
    border: 1px solid var(--border-color);
    padding: 16px;
}

.progress-bar {
    height: 2px;
    background: var(--border-color);
    width: 100%;
}

.progress-fill {
    height: 100%;
}

.score-high { color: var(--color-high); }
.score-high-bg { background-color: var(--color-high); }
.score-low { color: var(--color-low); }
.score-low-bg { background-color: var(--color-low); }

.badge {
    border: 1px solid var(--border-color);
    font-size: 9px;
    padding: 2px 6px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

.code-details summary {
    cursor: pointer;
    letter-spacing: 0.05em;
    color: var(--text-muted);
    list-style: none;
}
.code-details summary::-webkit-details-marker { display: none; }
.code-details summary:hover { color: var(--text-main); }

.code-block {
    background: var(--bg-main);
    border: 1px solid var(--border-color);
    padding: 12px;
    margin-top: 8px;
    overflow-x: auto;
    color: var(--text-muted);
}

.stats-panel {
    border: 1px solid var(--border-color);
    background: var(--bg-surface);
}

.stat-group {
    display: flex;
    border-bottom: 1px solid var(--border-color);
}

.stat-item {
    flex: 1;
    padding: 16px;
    text-align: center;
    border-right: 1px solid var(--border-color);
}
.stat-item:last-child { border-right: none; }
.stat-item .stat-value {
    display: block;
    font-family: var(--font-mono);
    font-size: 20px;
}
.stat-item .stat-label {
    font-size: 10px;
    color: var(--text-muted);
    letter-spacing: 0.1em;
}

.query-box {
    padding: 12px 16px;
    display: flex;
    gap: 12px;
    align-items: baseline;
}
.query-prompt {
    font-size: 10px;
    color: var(--text-muted);
    letter-spacing: 0.1em;
}
.query-text {
    font-size: 13px;
}

/* Confidence Symbols */
.symbol-badge {
    display: inline-flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    padding: 10px 12px;
    background: var(--bg-surface);
    border: 1px solid var(--border-color);
    font-size: 12px;
}
.badge-ok { border-left: 2px solid var(--status-ok); }
.badge-warn { border-left: 2px solid var(--status-warn); width: 100%; }
.badge-err { border-left: 2px solid var(--status-err); width: 100%; }

/* Buttons & Inputs */
.btn {
    background: transparent;
    color: var(--text-main);
    border: 1px solid var(--border-color);
    padding: 8px 16px;
    font-size: 11px;
    font-family: var(--font-sans);
    letter-spacing: 0.05em;
    text-transform: uppercase;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 6px;
}
.btn:hover {
    background: var(--bg-hover);
}
.btn-danger { color: var(--status-err); }
.btn-danger:hover {
    border-color: var(--status-err);
    background: transparent;
}

.dropzone {
    border: 1px dashed var(--border-color);
    padding: 40px 20px;
    text-align: center;
    cursor: pointer;
}
.dropzone:hover {
    border-color: var(--text-muted);
    background: var(--bg-surface);
}

.list-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 0;
    border-bottom: 1px solid var(--border-color);
}
.list-item:last-child { border-bottom: none; }

.empty-state {
    text-align: center;
    padding: 60px 20px;
}
.empty-icon {
    display: flex;
    justify-content: center;
    margin-bottom: 16px;
    color: var(--text-muted);
    opacity: 0.5;
}
.empty-icon svg { width: 32px; height: 32px; }

</style>
</head>
<body>

<div class="header">
    <div class="header-title">
        ${ICONS.database} CODERAG_ARCHITECT
    </div>
    <div class="nav-tabs">
        <button class="tab active" onclick="switchTab('context')" id="tab-context">
            ${ICONS.file} RETRIEVAL
        </button>
        <button class="tab" onclick="switchTab('confidence')" id="tab-confidence">
            ${ICONS.shield} VALIDATION
        </button>
        <button class="tab" onclick="switchTab('architect')" id="tab-architect">
            ${ICONS.box} ARCHITECT
        </button>
        <button class="tab" onclick="switchTab('memory')" id="tab-memory">
            ${ICONS.database} MEMORY
        </button>
    </div>
</div>

<div class="content-area">
    <div class="tab-pane active" id="content-context">
        ${this._getChunksHtml()}
    </div>

    <div class="tab-pane" id="content-confidence">
        ${this._getConfidenceHtml()}
    </div>

    <div class="tab-pane" id="content-architect">
        ${this._getArchitectHtml()}
    </div>

    <div class="tab-pane" id="content-memory">
        <div class="dropzone mb-6" onclick="handleUpload()">
            <div class="flex justify-center mb-2 color-muted">${ICONS.upload}</div>
            <div class="text-sm fw-500 mb-1">UPLOAD SOURCE MATERIAL</div>
            <div class="text-xs color-muted">SUPPORTED: PDF, MD, TXT, JSON</div>
        </div>

        <div class="flex gap-2 mb-6">
            <button class="btn" onclick="refreshMemory()">${ICONS.refresh} SYNC</button>
            <button class="btn btn-danger" onclick="clearMemory()">${ICONS.trash} PURGE</button>
        </div>

        <div class="mb-6">
            <div class="text-xs tracking-widest uppercase color-muted border-b pb-2 mb-2">Active Documents</div>
            <div id="docs-list" class="card">
                <div class="text-xs color-muted text-center py-6">NO DOCUMENTS INDEXED</div>
            </div>
        </div>

        <div>
            <div class="text-xs tracking-widest uppercase color-muted border-b pb-2 mb-2">Query Log</div>
            <div id="history-list" class="card">
                <div class="text-xs color-muted text-center py-6">LOG EMPTY</div>
            </div>
        </div>
    </div>
</div>

<script>
const vscode = acquireVsCodeApi();

function switchTab(tabName) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(c => c.classList.remove('active'));
    document.getElementById('tab-' + tabName).classList.add('active');
    document.getElementById('content-' + tabName).classList.add('active');
}

function handleUpload() {
    vscode.postMessage({ command: 'uploadDoc' });
}

function refreshMemory() {
    vscode.postMessage({ command: 'refreshMemory' });
}

function clearMemory() {
    vscode.postMessage({ command: 'clearMemory' });
}

function deleteDoc(docId) {
    vscode.postMessage({ command: 'deleteDoc', docId });
}

window.addEventListener('message', event => {
    const msg = event.data;
    if (msg.type === 'memoryUpdate') {
        renderDocs(msg.documents || []);
        renderHistory(msg.history || []);
    } else if (msg.command === 'switchTab') {
        switchTab(msg.tab);
    }
});

const icons = {
    doc: \`${ICONS.doc}\`,
    box: \`${ICONS.box}\`,
    clock: \`${ICONS.clock}\`,
    file: \`${ICONS.file}\`
};

function renderDocs(docs) {
    const container = document.getElementById('docs-list');
    if (docs.length === 0) {
        container.innerHTML = '<div class="text-xs color-muted text-center py-4">NO DOCUMENTS INDEXED</div>';
        return;
    }
    container.innerHTML = docs.map(d => {
        const date = new Date(d.uploaded_at * 1000).toLocaleTimeString();
        return \`
            <div class="list-item">
                <div class="flex-col gap-1">
                    <div class="flex align-center gap-2 text-sm fw-500"><span class="color-muted">\${icons.doc}</span> \${escapeHtml(d.name)}</div>
                    <div class="text-xs color-muted font-mono">CHUNKS:\${d.chunk_count} | \${date}</div>
                </div>
                <button class="btn btn-danger" style="padding: 4px 8px; font-size: 9px;" onclick="deleteDoc('\${d.doc_id}')">REMOVE</button>
            </div>
        \`;
    }).join('');
}

function renderHistory(history) {
    const container = document.getElementById('history-list');
    if (history.length === 0) {
        container.innerHTML = '<div class="text-xs color-muted text-center py-4">LOG EMPTY</div>';
        return;
    }
    container.innerHTML = history.map(h => {
        const date = new Date(h.timestamp * 1000).toLocaleTimeString();
        const confText = h.confidence !== null ? \`VAL:\${Math.round(h.confidence * 100)}%\` : '';
        return \`
            <div class="list-item flex-col" style="align-items: flex-start; gap: 8px;">
                <div class="text-sm">\${escapeHtml(h.query)}</div>
                <div class="flex gap-4 text-xs font-mono color-muted w-full">
                    <span class="flex align-center gap-1">\${icons.box}\${h.chunk_count}</span>
                    <span class="flex align-center gap-1">\${icons.file}\${h.sources.length}</span>
                    \${confText ? \`<span>\${confText}</span>\` : ''}
                    \${h.has_doc_results ? \'<span class="badge">DOC</span>\' : ''}
                    <span class="ml-auto flex align-center gap-1">\${icons.clock}\${date}</span>
                </div>
            </div>
        \`;
    }).join('');
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}
</script>

</body>
</html>`;
    }

    public dispose() {
        CodeRAGDashboard.currentPanel = undefined;
        this._panel.dispose();
        while (this._disposables.length) {
            const d = this._disposables.pop();
            if (d) d.dispose();
        }
    }
}
