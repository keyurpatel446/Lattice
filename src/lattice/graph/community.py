"""Community detection over a CSR snapshot.

Uses a single-level **Louvain local-move** pass — greedily moving each node to
the neighboring community that maximizes modularity gain. It is near-linear in
practice, dependency-free, and a natural fit for the CSR layout (neighbor scans
are contiguous slices). Unlike naive label propagation, it does not collapse
weakly-connected clusters across a single bridge edge.

This is the fast default; a Leiden adapter can implement the same `detect()`
contract for higher-quality clustering when the `igraph` extra is installed.

Determinism: node visit order and tie-breaking are sorted, so repeated runs on
the same graph yield identical labels.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace

from ..domain.models import GraphSnapshot, Node


def _undirected_adjacency(snapshot: GraphSnapshot) -> list[list[int]]:
    """Build symmetric neighbor lists by index from the directed CSR arrays."""
    n = len(snapshot.order)
    adj: list[set[int]] = [set() for _ in range(n)]
    for i in range(n):
        for j in snapshot.indices[snapshot.indptr[i]:snapshot.indptr[i + 1]]:
            if i != j:
                adj[i].add(j)
                adj[j].add(i)
    return [sorted(s) for s in adj]


def detect(snapshot: GraphSnapshot, max_iter: int = 50) -> dict[str, int]:
    """Return a mapping of node id -> community id (small ints, gap-free)."""
    n = len(snapshot.order)
    if n == 0:
        return {}

    adj = _undirected_adjacency(snapshot)
    degree = [len(neigh) for neigh in adj]
    m = sum(degree) / 2.0
    if m == 0:  # no edges → every node is its own community
        return {node_id: i for i, node_id in enumerate(snapshot.order)}

    comm = list(range(n))           # node -> community
    sigma_tot = [float(d) for d in degree]  # total degree per community
    two_m = 2.0 * m

    for _ in range(max_iter):
        improved = False
        for i in range(n):          # deterministic sweep
            ci = comm[i]
            sigma_tot[ci] -= degree[i]   # tentatively remove i from its community

            # Sum of edges from i into each neighboring community.
            links: Counter[int] = Counter()
            for j in adj[i]:
                links[comm[j]] += 1

            # Modularity gain (shared 1/m factor dropped — only ranking matters).
            best_c, best_gain = ci, links[ci] - degree[i] * sigma_tot[ci] / two_m
            for c, w_in in links.items():
                gain = w_in - degree[i] * sigma_tot[c] / two_m
                if gain > best_gain + 1e-12 or (
                        abs(gain - best_gain) <= 1e-12 and c < best_c):
                    best_c, best_gain = c, gain

            comm[i] = best_c
            sigma_tot[best_c] += degree[i]
            if best_c != ci:
                improved = True
        if not improved:
            break

    # Compact labels to a dense 0..k range for stable, readable ids.
    remap: dict[int, int] = {}
    result: dict[str, int] = {}
    for i, node_id in enumerate(snapshot.order):
        cid = remap.setdefault(comm[i], len(remap))
        result[node_id] = cid
    return result


def annotate(snapshot: GraphSnapshot,
             communities: dict[str, int]) -> GraphSnapshot:
    """Return a new snapshot with each node's `meta['community']` set."""
    new_nodes: dict[str, Node] = {}
    for node_id, node in snapshot.nodes.items():
        meta = {**node.meta, "community": communities.get(node_id, -1)}
        new_nodes[node_id] = replace(node, meta=meta)
    return replace(snapshot, nodes=new_nodes)
