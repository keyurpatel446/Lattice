"""Renderer adapter — Mermaid flowchart export.

Groups nodes into `subgraph` blocks by community (when annotated) so the diagram
reads as an architecture map. Mermaid degrades on huge graphs, so output is
capped by `max_nodes` (highest-degree nodes win).
"""

from __future__ import annotations

import re
from collections import Counter

from ..domain.models import GraphSnapshot

_SAFE = re.compile(r"[^A-Za-z0-9]")


def _safe_id(node_id: str) -> str:
    return "n_" + _SAFE.sub("_", node_id)


def _label(text: str) -> str:
    # Mermaid chokes on quotes/brackets in labels; escape to entities.
    return text.replace('"', "&quot;").replace("[", "(").replace("]", ")")


class MermaidRenderer:
    def __init__(self, max_nodes: int = 120) -> None:
        self._max_nodes = max_nodes

    def render(self, snapshot: GraphSnapshot, out_path: str) -> str:
        kept = self._top_nodes(snapshot)
        lines = ["flowchart LR"]

        # Group kept nodes by community for subgraph blocks.
        by_comm: dict[int, list[str]] = {}
        for nid in kept:
            comm = snapshot.nodes[nid].meta.get("community", -1)
            by_comm.setdefault(comm, []).append(nid)

        for comm, ids in sorted(by_comm.items()):
            if comm >= 0:
                lines.append(f"  subgraph cluster_{comm}[Community {comm}]")
                indent = "    "
            else:
                indent = "  "
            for nid in ids:
                node = snapshot.nodes[nid]
                lines.append(f'{indent}{_safe_id(nid)}["{_label(node.label)}"]')
            if comm >= 0:
                lines.append("  end")

        for edge in snapshot.edges:
            if edge.source in kept and edge.target in kept:
                lines.append(
                    f"  {_safe_id(edge.source)} -->|{_label(edge.relation)}| "
                    f"{_safe_id(edge.target)}"
                )

        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        return out_path

    def _top_nodes(self, snapshot: GraphSnapshot) -> set[str]:
        """Pick the highest-degree nodes so the diagram stays legible."""
        degree: Counter[str] = Counter()
        for edge in snapshot.edges:
            degree[edge.source] += 1
            degree[edge.target] += 1
        ranked = sorted(snapshot.nodes,
                        key=lambda nid: (-degree[nid], nid))
        return set(ranked[: self._max_nodes])
