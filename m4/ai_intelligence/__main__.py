import argparse
import json
from pathlib import Path
import sys

from pydantic import ValidationError

from .context import ContextError, RepositoryContext
from .contracts import Finding, SourceRange
from .embeddings import MODEL_ID, LocalEmbedder
from .gemini import Gemini, ProviderError
from .providers import PROVIDERS, create_generator
from .review import explain, semgrep_findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Codely M4 repository context and defensive review")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check-gemini", help="Check model metadata without uploading repository source")
    for name in ("index", "context", "review"):
        command = commands.add_parser(name)
        command.add_argument("repo", type=Path)
        command.add_argument("--project", default="local")
        semantic = command.add_mutually_exclusive_group()
        semantic.add_argument("--semantic-gemini", action="store_true",
                             help="Send filtered source chunks to Gemini to build an in-memory FAISS index")
        semantic.add_argument("--semantic-local", nargs="?", const=MODEL_ID, metavar="MODEL_PATH",
                              help="Build a FAISS index using local MiniLM model files")
        if name == "context":
            command.add_argument("path")
            command.add_argument("start_line", type=int)
            command.add_argument("end_line", type=int)
            command.add_argument("--query", default="")
        if name == "review":
            command.add_argument("findings", type=Path)
            command.add_argument("--format", choices=["normalized", "semgrep"], default="normalized")
            generation = command.add_mutually_exclusive_group()
            generation.add_argument("--gemini", action="store_const", const="gemini", dest="provider",
                                 help="Send filtered evidence to Gemini for a live review")
            generation.add_argument("--provider", choices=PROVIDERS,
                                    help="Override M4_PROVIDER for this review")
    args = parser.parse_args()
    try:
        if args.command == "check-gemini":
            print(json.dumps(Gemini().check()))
            return 0
        embedder = None
        if args.semantic_gemini:
            embedder = Gemini()
        elif args.semantic_local:
            embedder = LocalEmbedder(args.semantic_local)
        context = RepositoryContext(args.project, args.repo, embedder=embedder)
        if args.command == "index":
            result = {"project_id": context.project_id, "files": len(context.files),
                      "chunks": len(context.chunks), "semantic_status": context.semantic_status,
                      "skipped": dict(context.skipped)}
        elif args.command == "context":
            span = SourceRange(path=args.path, start_line=args.start_line, end_line=args.end_line)
            result = [item.model_dump() for item in context.retrieve(span, args.query)]
        else:
            raw = json.loads(args.findings.read_text(encoding="utf-8"))
            if args.format == "semgrep":
                findings = semgrep_findings(raw)
            else:
                if not isinstance(raw, list):
                    raise ContextError("Expected a normalized findings array")
                findings = [Finding.model_validate(item) for item in raw]
            results, failures = [], []
            generator = create_generator(args.provider)
            try:
                for finding in findings:
                    try:
                        results.append(explain(context, finding, generator).model_dump())
                    except (ContextError, ProviderError) as error:
                        failures.append({"scanner_finding": finding.model_dump(), "error": str(error)})
            finally:
                close = getattr(generator, "close", None)
                if close is not None:
                    close()
            result = {"scanner_count": len(findings), "mode": generator.mode,
                      "semantic_status": context.semantic_status, "reviews": results,
                      "failures": failures}
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return int(bool(result.get("failures"))) if isinstance(result, dict) else 0
    except (ValidationError, ContextError, ProviderError, OSError, ValueError, KeyError, TypeError) as error:
        if isinstance(error, (ContextError, ProviderError)):
            print(str(error), file=sys.stderr)
        else:
            print("Could not read or validate the requested inputs", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
