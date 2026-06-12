"""Composition root + CLI.

This is the ONLY place concrete adapters are named and wired together. Swapping
an implementation (serial vs pool scheduler, CSR vs Neo4j store, JSON vs HTML
renderer) is a change here and nowhere else.
"""

from __future__ import annotations

import argparse
import os
import sys

from ..cache.fingerprint import InMemoryFingerprintCache
from ..enrich.llm_port import NullEnricher
from ..extract.registry import extract_one, register
from ..extract.extractors.python_ast import PythonAstExtractor
from ..extract.extractors.treesitter import TreeSitterExtractor
from ..graph import community
from ..graph.csr_store import CsrGraphStore
from ..ingest.discovery import FileSystemDiscovery
from ..pipeline.orchestrator import Pipeline
from ..pipeline.scheduler import ProcessPoolScheduler, SerialScheduler
from ..render.html_writer import HtmlRenderer
from ..render.json_writer import JsonRenderer
from ..render.mermaid_writer import MermaidRenderer

# Register extractors (Open/Closed: extend by adding lines here, not editing core).
# Order = priority: the native Python AST is preferred; tree-sitter covers the
# rest, and quietly no-ops if its grammars aren't installed.
register(PythonAstExtractor())
register(TreeSitterExtractor())

# Renderer registry — one adapter per format, all behind the Renderer port.
_RENDERERS = {
    "json": (JsonRenderer, ".graph.json"),
    "html": (HtmlRenderer, ".graph.html"),
    "mermaid": (MermaidRenderer, ".graph.mmd"),
}


def build_pipeline(serial: bool) -> Pipeline:
    scheduler = SerialScheduler() if serial else ProcessPoolScheduler()
    return Pipeline(
        discovery=FileSystemDiscovery(),
        scheduler=scheduler,
        store=CsrGraphStore(),
        extract_fn=extract_one,
        cache=InMemoryFingerprintCache(),
        enricher=NullEnricher(),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lattice",
                                     description="Build a code knowledge graph.")
    parser.add_argument("root", help="directory to analyze")
    parser.add_argument("-o", "--out", default="lattice",
                        help="output path prefix (extension added per format)")
    parser.add_argument("-f", "--format", default=["json"], nargs="+",
                        choices=sorted(_RENDERERS), help="output format(s)")
    parser.add_argument("--communities", action="store_true",
                        help="run community detection and annotate nodes")
    parser.add_argument("--serial", action="store_true",
                        help="disable the process pool (deterministic)")
    args = parser.parse_args(argv)

    pipeline = build_pipeline(serial=args.serial)
    snapshot = pipeline.run(args.root)

    if args.communities:
        communities = community.detect(snapshot)
        snapshot = community.annotate(snapshot, communities)
        n_comm = len(set(communities.values()))
        print(f"communities={n_comm}")

    outputs = []
    for fmt in args.format:
        renderer_cls, suffix = _RENDERERS[fmt]
        out_path = f"{args.out}{suffix}" if not os.path.splitext(args.out)[1] \
            else args.out
        outputs.append(renderer_cls().render(snapshot, out_path))

    print(f"nodes={len(snapshot.nodes)} edges={len(snapshot.edges)} -> "
          f"{', '.join(outputs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
