"""Tests for community detection, renderers, and tree-sitter graceful fallback."""

from __future__ import annotations

import json

from lattice.domain.models import Edge, Fragment, Node, SourceFile
from lattice.extract.extractors.treesitter import TreeSitterExtractor
from lattice.graph import community
from lattice.graph.csr_store import CsrGraphStore
from lattice.render.html_writer import HtmlRenderer
from lattice.render.json_writer import JsonRenderer
from lattice.render.mermaid_writer import MermaidRenderer


def _two_cluster_snapshot():
    """Two triangles joined by a single bridge edge -> two communities."""
    store = CsrGraphStore()
    nodes = [Node(id=x, label=x, kind="function", path="f") for x in "ABCDEF"]
    edges = [
        Edge("A", "B", "calls"), Edge("B", "C", "calls"), Edge("C", "A", "calls"),
        Edge("D", "E", "calls"), Edge("E", "F", "calls"), Edge("F", "D", "calls"),
        Edge("C", "D", "calls"),  # bridge
    ]
    store.add(Fragment(path="f", fingerprint="x", nodes=nodes, edges=edges))
    return store.snapshot()


def test_community_detection_separates_clusters():
    snap = _two_cluster_snapshot()
    communities = community.detect(snap)
    assert communities["A"] == communities["B"] == communities["C"]
    assert communities["D"] == communities["E"] == communities["F"]
    assert communities["A"] != communities["D"]


def test_annotate_sets_meta():
    snap = _two_cluster_snapshot()
    annotated = community.annotate(snap, community.detect(snap))
    assert all("community" in n.meta for n in annotated.nodes.values())


def test_renderers_write_files(tmp_path):
    snap = community.annotate(_two_cluster_snapshot(),
                              community.detect(_two_cluster_snapshot()))

    jpath = JsonRenderer().render(snap, str(tmp_path / "g.json"))
    assert json.load(open(jpath))["stats"]["node_count"] == 6

    mpath = MermaidRenderer().render(snap, str(tmp_path / "g.mmd"))
    assert open(mpath).read().startswith("flowchart LR")

    hpath = HtmlRenderer().render(snap, str(tmp_path / "g.html"))
    html = open(hpath).read()
    assert "<canvas" in html and "application/json" in html


def test_treesitter_degrades_without_grammars():
    """Registering/using tree-sitter must never crash when deps are absent."""
    ext = TreeSitterExtractor()
    f = SourceFile(path="x.go", language="go", size=0, fingerprint="x")
    # supports() is False without grammars; extract() returns an empty fragment.
    if not ext.supports(f):
        frag = ext.extract(f)
        assert frag.nodes == [] and frag.edges == []
