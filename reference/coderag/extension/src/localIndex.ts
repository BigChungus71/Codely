import * as vscode from 'vscode';
import axios from 'axios';

interface Chunk {
    file: string;
    text: string;
}

interface IndexData {
    chunks: Chunk[];
    embeddings: number[][]; // 2D array: [chunk_index][embedding_dim]
}

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

export interface SearchResult {
    context: string;
    sources: string[];
    chunks: ChunkDetail[];
    confidence: ConfidenceReport;
    retrievalTimeMs: number;
}

const INDEX_FILE_NAME = 'coderag.index.json';

/**
 * Split text into overlapping line-based chunks.
 */
function chunkText(text: string, filePath: string, linesPerChunk = 50, overlap = 10): Chunk[] {
    const lines = text.split('\n');
    const chunks: Chunk[] = [];
    
    if (lines.length === 0) return chunks;

    for (let i = 0; i < lines.length; i += (linesPerChunk - overlap)) {
        let chunkLines = lines.slice(i, i + linesPerChunk);
        let joinedText = chunkLines.join('\n').trim();
        
        // Safety: truncate over-sized chunks to stay within payload limits.
        if (joinedText.length > 3000) {
            joinedText = joinedText.slice(0, 3000) + '...[truncated]';
        }

        if (joinedText.length > 0) {
            chunks.push({
                file: filePath,
                text: joinedText
            });
        }
        
        if (i + linesPerChunk >= lines.length) {
            break;
        }
    }
    return chunks;
}

/**
 * Compute cosine similarity between two vectors.
 */
function cosineSimilarity(vecA: number[], vecB: number[]): number {
    let dotProduct = 0;
    let normA = 0;
    let normB = 0;
    for (let i = 0; i < vecA.length; i++) {
        dotProduct += vecA[i] * vecB[i];
        normA += vecA[i] * vecA[i];
        normB += vecB[i] * vecB[i];
    }
    if (normA === 0 || normB === 0) return 0;
    return dotProduct / (Math.sqrt(normA) * Math.sqrt(normB));
}

/**
 * Local hallucination check — lightweight client-side validation.
 * Checks if symbols in the formatted context appear consistent.
 */
function localConfidenceCheck(context: string, chunks: ChunkDetail[]): ConfidenceReport {
    const chunkText = chunks.map(c => c.text).join('\n');
    
    // Extract import-like patterns from context
    const importPattern = /(?:import|from)\s+([\w.]+)/g;
    const fnPattern = /\b([a-z_][a-zA-Z0-9_]*)\s*\(/g;
    
    const verified: { symbol: string; type: string }[] = [];
    const warnings: { symbol: string; type: string; reason: string }[] = [];
    
    const stdlibs = new Set(['os', 'sys', 're', 'json', 'time', 'math', 'random', 'typing', 'collections', 'datetime', 'pathlib', 'io', 'abc', 'logging', 'functools', 'itertools']);
    const builtins = new Set(['print', 'len', 'range', 'str', 'int', 'float', 'list', 'dict', 'open', 'type', 'isinstance', 'enumerate', 'zip', 'map', 'filter', 'sorted', 'any', 'all', 'sum', 'min', 'max', 'abs', 'format', 'input', 'super', 'getattr', 'setattr', 'hasattr']);
    
    // Check imports
    let match;
    const seenImports = new Set<string>();
    while ((match = importPattern.exec(context)) !== null) {
        const imp = match[1];
        if (seenImports.has(imp)) continue;
        seenImports.add(imp);
        
        const root = imp.split('.')[0];
        if (stdlibs.has(root)) {
            verified.push({ symbol: imp, type: 'import' });
        } else if (chunkText.includes(imp)) {
            verified.push({ symbol: imp, type: 'import' });
        } else {
            warnings.push({ symbol: imp, type: 'import', reason: `Module '${imp}' not found in retrieved chunks` });
        }
    }
    
    // Check functions
    const seenFns = new Set<string>();
    while ((match = fnPattern.exec(context)) !== null) {
        const fn = match[1];
        if (seenFns.has(fn) || builtins.has(fn)) continue;
        seenFns.add(fn);
        
        if (chunkText.includes(fn)) {
            verified.push({ symbol: `${fn}()`, type: 'function' });
        }
    }
    
    const total = verified.length + warnings.length;
    const score = total === 0 ? 1.0 : Math.round((verified.length / total) * 100) / 100;
    
    return {
        overall_confidence: score,
        level: score >= 0.75 ? 'high' : score >= 0.45 ? 'medium' : 'low',
        verified,
        warnings,
        errors: [],
        stats: {
            total_symbols: total,
            verified_count: verified.length,
            warning_count: warnings.length,
            error_count: 0
        }
    };
}

export async function indexWorkspace(
    context: vscode.ExtensionContext, 
    backendUrl: string, 
    onProgress: (msg: string) => void
): Promise<number> {
    if (!context.storageUri) {
        throw new Error("No storage URI available for this workspace.");
    }

    await vscode.workspace.fs.createDirectory(context.storageUri);

    onProgress("Discovering files (skipping binaries & node_modules)...");
    
    // Comprehensive exclusion list for performance
    const excludePattern = '{**/node_modules/**,**/.git/**,**/dist/**,**/out/**,**/build/**,**/.next/**,**/.nuxt/**,**/.venv/**,**/venv/**,**/__pycache__/**,**/target/**,**/vendor/**,**/*.png,**/*.jpg,**/*.jpeg,**/*.gif,**/*.svg,**/*.ico,**/*.woff,**/*.woff2,**/*.ttf,**/*.eot,**/*.pdf,**/*.zip,**/*.tar,**/*.gz,**/*.min.js,**/*.min.css,**/*.map,**/*.lock,**/*.exe,**/*.dll,**/*.so,**/*.dylib,**/*.bin,**/*.pyc,**/*.pyo,**/*.db,**/*.sqlite}';

    const files = await vscode.workspace.findFiles('**/*.*', excludePattern);

    if (files.length === 0) {
        throw new Error("No indexable files found in the workspace.");
    }

    onProgress(`Reading ${files.length} files in parallel...`);
    let allChunks: Chunk[] = [];

    // Parallel file processing for high-speed indexing
    const fileContents = await Promise.all(
        files.map(async (fileUri) => {
            try {
                const stat = await vscode.workspace.fs.stat(fileUri);
                if (stat.size > 1024 * 1024) return null;
                
                const fileBytes = await vscode.workspace.fs.readFile(fileUri);
                const text = new TextDecoder().decode(fileBytes);
                if (text.trim().length === 0) return null;

                const workspaceFolder = vscode.workspace.getWorkspaceFolder(fileUri);
                const relPath = workspaceFolder ? vscode.workspace.asRelativePath(fileUri) : fileUri.fsPath;
                return { text, relPath };
            } catch (e) {
                return null;
            }
        })
    );

    onProgress(`Chunking code content...`);
    for (const content of fileContents) {
        if (content) {
            const fileChunks = chunkText(content.text, content.relPath);
            allChunks = allChunks.concat(fileChunks);
        }
    }

    if (allChunks.length === 0) {
        throw new Error("Found files but no indexable text content. Check your repo.");
    }

    onProgress(`Generating embeddings for ${allChunks.length} chunks...`);
    
    const BATCH_SIZE = 12; // Optimized for reliability vs speed
    let allEmbeddings: number[][] = [];

    for (let i = 0; i < allChunks.length; i += BATCH_SIZE) {
        const batch = allChunks.slice(i, i + BATCH_SIZE);
        const batchTexts = batch.map(c => c.text);
        
        onProgress(`Batch ${Math.floor(i / BATCH_SIZE) + 1} of ${Math.ceil(allChunks.length / BATCH_SIZE)}...`);
        
        let success = false;
        let retries = 3;
        while (!success && retries > 0) {
            try {
                const response = await axios.post(`${backendUrl}/embed`, {
                    texts: batchTexts,
                    input_type: "passage"
                }, { timeout: 120000 }); // Increased to 2 minutes for large batches

                const embeddings: number[][] = response.data.embeddings;
                allEmbeddings = allEmbeddings.concat(embeddings);
                success = true;
            } catch (err: any) {
                retries--;
                if (retries === 0) {
                    throw new Error(`Embedding failed: ${err.message}. Check backend logs.`);
                }
                onProgress(`Retrying batch... (${retries} left)`);
                await new Promise(res => setTimeout(res, 2000));
            }
        }
    }

    const indexData: IndexData = {
        chunks: allChunks,
        embeddings: allEmbeddings
    };

    onProgress("Saving optimized index locally...");
    const indexUri = vscode.Uri.joinPath(context.storageUri, INDEX_FILE_NAME);
    const indexBytes = new TextEncoder().encode(JSON.stringify(indexData));
    await vscode.workspace.fs.writeFile(indexUri, indexBytes);

    return allChunks.length;
}

export async function searchIndex(
    context: vscode.ExtensionContext,
    backendUrl: string,
    query: string,
    topK: number = 10
): Promise<SearchResult> {
    if (!context.storageUri) {
        throw new Error("Workspace not active.");
    }

    const indexUri = vscode.Uri.joinPath(context.storageUri, INDEX_FILE_NAME);
    let indexData: IndexData;

    try {
        const indexBytes = await vscode.workspace.fs.readFile(indexUri);
        indexData = JSON.parse(new TextDecoder().decode(indexBytes)) as IndexData;
    } catch (e) {
        throw new Error("Local index not found. Please run 'CodeRAG: Index Workspace'.");
    }

    const startTime = Date.now();

    const response = await axios.post(`${backendUrl}/embed`, {
        texts: [query],
        input_type: "query"
    });
    const queryEmbedding: number[] = response.data.embeddings[0];

    // Speed-optimized cosine similarity loop
    const scoredChunks = indexData.chunks.map((chunk, i) => ({
        chunk,
        sim: cosineSimilarity(queryEmbedding, indexData.embeddings[i]),
        index: i
    }));

    scoredChunks.sort((a, b) => b.sim - a.sim);
    const topChunks = scoredChunks.slice(0, topK);

    const retrievalTimeMs = Date.now() - startTime;

    // Build formatted context
    let formattedContext = "";
    const sourcesSet = new Set<string>();
    const chunkDetails: ChunkDetail[] = [];

    for (const sc of topChunks) {
        formattedContext += `\n--- File: ${sc.chunk.file} ---\n${sc.chunk.text}\n`;
        sourcesSet.add(sc.chunk.file);

        chunkDetails.push({
            file: sc.chunk.file,
            start_line: sc.index * 20, // Approximate line from chunk index
            text: sc.chunk.text.length > 500 ? sc.chunk.text.slice(0, 500) + '...' : sc.chunk.text,
            score: Math.round(sc.sim * 100) / 100,
            source_type: 'code'
        });
    }

    // Run local confidence check
    const confidence = localConfidenceCheck(formattedContext, chunkDetails);

    return {
        context: formattedContext.trim(),
        sources: Array.from(sourcesSet),
        chunks: chunkDetails,
        confidence,
        retrievalTimeMs
    };
}
