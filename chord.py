"""
chord.py — Core Chord DHT logic (no SimPy, no UI).

Implements:
  - Consistent hashing with M-bit identifiers
  - Finger tables
  - Successor / predecessor pointers
  - Key lookup routing (iterative)
  - Node join / graceful departure
"""

import hashlib
import math
from dataclasses import dataclass, field
from typing import Optional


def sha1_id(key: str, m: int) -> int:
    """Hash an arbitrary string to a M-bit Chord identifier."""
    digest = int(hashlib.sha1(key.encode()).hexdigest(), 16)
    return digest % (2 ** m)


def in_range(x: int, a: int, b: int, m: int, inclusive_b: bool = False) -> bool:
    """
    True if x is in the circular interval (a, b] on a 2^m ring.
    If inclusive_b is False → open interval (a, b).
    """
    ring = 2 ** m
    a, b, x = a % ring, b % ring, x % ring
    if a == b:
        return True  # full ring
    if a < b:
        return (a < x < b) if not inclusive_b else (a < x <= b)
    else:  # wraps around
        return (x > a or x < b) if not inclusive_b else (x > a or x <= b)


@dataclass
class FingerEntry:
    start: int          # (n + 2^(k-1)) mod 2^m
    node: Optional[int] = None   # id of responsible node


class ChordNode:
    def __init__(self, node_id: int, m: int):
        self.id = node_id
        self.m = m
        self.ring_size = 2 ** m
        self.finger: list[FingerEntry] = []
        self.successor: Optional[int] = None
        self.predecessor: Optional[int] = None
        self._init_finger_table()

    def _init_finger_table(self):
        self.finger = [
            FingerEntry(start=(self.id + 2 ** k) % self.ring_size)
            for k in range(self.m)
        ]

    def find_successor_local(self, key_id: int, ring: "ChordRing") -> tuple[int, list[int]]:
        """
        Iterative lookup. Returns (responsible_node_id, [hops]).
        """
        hops = [self.id]
        current_id = self.id
        current_node = self

        for _ in range(self.m + 1):          # at most O(log N) hops
            succ = current_node.successor
            if succ is None:
                break
            # Is the key between current and its successor?
            if in_range(key_id, current_node.id, succ, self.m, inclusive_b=True):
                hops.append(succ)
                return succ, hops
            # Forward to the closest preceding finger
            next_id = current_node._closest_preceding_finger(key_id)
            if next_id == current_node.id:
                hops.append(succ)
                return succ, hops
            hops.append(next_id)
            current_node = ring.nodes[next_id]
            current_id = next_id

        return current_node.id, hops

    def _closest_preceding_finger(self, key_id: int) -> int:
        for k in range(self.m - 1, -1, -1):
            f = self.finger[k].node
            if f is not None and in_range(f, self.id, key_id, self.m):
                return f
        return self.id


class ChordRing:
    """
    Manages a collection of ChordNodes on a single logical ring.
    """

    def __init__(self, m: int = 6):
        self.m = m
        self.ring_size = 2 ** m
        self.nodes: dict[int, ChordNode] = {}

    # ------------------------------------------------------------------ #
    #  Node management
    # ------------------------------------------------------------------ #

    def add_node(self, node_id: int):
        """Insert a node and rebuild all finger tables."""
        if node_id in self.nodes:
            raise ValueError(f"Node {node_id} already exists.")
        node = ChordNode(node_id, self.m)
        self.nodes[node_id] = node
        self._rebuild_ring()

    def remove_node(self, node_id: int):
        """Remove a node and rebuild all finger tables."""
        if node_id not in self.nodes:
            raise ValueError(f"Node {node_id} not found.")
        del self.nodes[node_id]
        self._rebuild_ring()

    def _sorted_ids(self) -> list[int]:
        return sorted(self.nodes.keys())

    def _rebuild_ring(self):
        """Recompute successor, predecessor, and finger tables for all nodes."""
        ids = self._sorted_ids()
        n = len(ids)
        if n == 0:
            return

        for i, nid in enumerate(ids):
            node = self.nodes[nid]
            node.successor = ids[(i + 1) % n]
            node.predecessor = ids[(i - 1) % n]

        for nid in ids:
            node = self.nodes[nid]
            for k in range(self.m):
                start = node.finger[k].start
                node.finger[k].node = self._find_successor_id(start)

    def _find_successor_id(self, key_id: int) -> int:
        """Return the node responsible for key_id (simple scan)."""
        ids = self._sorted_ids()
        for nid in ids:
            if nid >= key_id:
                return nid
        return ids[0]   # wrap around

    # ------------------------------------------------------------------ #
    #  Lookup
    # ------------------------------------------------------------------ #

    def lookup(self, key: str, start_node_id: Optional[int] = None) -> dict:
        """
        Perform a Chord lookup for `key`.
        Returns a dict with hop trace, responsible node, and key_id.
        """
        key_id = sha1_id(key, self.m)
        ids = self._sorted_ids()
        if not ids:
            return {"key": key, "key_id": key_id, "hops": [], "responsible": None}

        if start_node_id is None or start_node_id not in self.nodes:
            start_node_id = ids[0]

        start_node = self.nodes[start_node_id]
        responsible, hops = start_node.find_successor_local(key_id, self)
        return {
            "key": key,
            "key_id": key_id,
            "start": start_node_id,
            "hops": hops,
            "responsible": responsible,
            "hop_count": len(hops) - 1,
        }

    # ------------------------------------------------------------------ #
    #  Introspection helpers
    # ------------------------------------------------------------------ #

    def finger_table(self, node_id: int) -> list[dict]:
        node = self.nodes[node_id]
        return [
            {"k": k + 1,
             "start": entry.start,
             "interval_end": node.finger[(k + 1) % self.m].start if self.m > 1 else entry.start,
             "node": entry.node}
            for k, entry in enumerate(node.finger)
        ]

    def node_list(self) -> list[dict]:
        ids = self._sorted_ids()
        result = []
        for nid in ids:
            node = self.nodes[nid]
            result.append({
                "id": nid,
                "successor": node.successor,
                "predecessor": node.predecessor,
            })
        return result
