"""
simulation.py — SimPy discrete-event simulation of Chord lookups.

Models:
  - Network latency between hops (configurable per-hop delay)
  - Concurrent lookup requests arriving at random nodes
  - Collects latency statistics per lookup
"""

import simpy
import random
from chord import ChordRing, sha1_id
from dataclasses import dataclass, field


HOP_DELAY_MS = 10          # simulated milliseconds per network hop


@dataclass
class LookupEvent:
    lookup_id: int
    key: str
    key_id: int
    start_node: int
    hops: list
    responsible: int
    hop_count: int
    arrival_time: float
    completion_time: float = 0.0
    latency_ms: float = 0.0


def lookup_process(env: simpy.Environment,
                   ring: ChordRing,
                   key: str,
                   start_node_id: int,
                   lookup_id: int,
                   results: list,
                   hop_delay: float = HOP_DELAY_MS):
    """SimPy process: simulate one key lookup with hop-by-hop delays."""
    arrival = env.now
    result = ring.lookup(key, start_node_id)

    # Simulate each hop taking `hop_delay` ms
    for _ in range(result["hop_count"]):
        yield env.timeout(hop_delay)

    completion = env.now
    event = LookupEvent(
        lookup_id=lookup_id,
        key=key,
        key_id=result["key_id"],
        start_node=start_node_id,
        hops=result["hops"],
        responsible=result["responsible"],
        hop_count=result["hop_count"],
        arrival_time=arrival,
        completion_time=completion,
        latency_ms=completion - arrival,
    )
    results.append(event)


def run_simulation(ring: ChordRing,
                   keys: list[str],
                   hop_delay: float = HOP_DELAY_MS,
                   inter_arrival: float = 5.0,
                   seed: int = 42) -> list[LookupEvent]:
    """
    Run a SimPy simulation for a batch of key lookups.

    Parameters
    ----------
    ring           : ChordRing instance (already populated with nodes)
    keys           : list of keys to look up
    hop_delay      : simulated ms per hop
    inter_arrival  : mean ms between successive lookup arrivals (Poisson)
    seed           : random seed for reproducibility

    Returns
    -------
    List of LookupEvent objects, one per lookup.
    """
    rng = random.Random(seed)
    env = simpy.Environment()
    node_ids = list(ring.nodes.keys())
    results: list[LookupEvent] = []

    def arrival_generator():
        for i, key in enumerate(keys):
            # Random start node
            start = rng.choice(node_ids)
            env.process(lookup_process(env, ring, key, start, i, results, hop_delay))
            # Poisson inter-arrival
            yield env.timeout(rng.expovariate(1.0 / inter_arrival))

    env.process(arrival_generator())
    env.run()
    return results


def scaling_experiment(m: int = 6,
                       node_counts: list[int] | None = None,
                       lookups_per_size: int = 50,
                       hop_delay: float = HOP_DELAY_MS,
                       seed: int = 42) -> list[dict]:
    """
    Measure average hop count as N (number of nodes) varies.
    Returns list of {"n_nodes": ..., "avg_hops": ..., "log2_n": ...}.
    """
    if node_counts is None:
        node_counts = [2, 4, 8, 16, 32, 48, 64]

    rng = random.Random(seed)
    results = []

    for n in node_counts:
        ring = ChordRing(m=m)
        # Pick n distinct random IDs in [0, 2^m)
        ids = rng.sample(range(2 ** m), min(n, 2 ** m))
        for nid in ids:
            ring.add_node(nid)

        keys = [f"key_{rng.randint(0, 10000)}" for _ in range(lookups_per_size)]
        events = run_simulation(ring, keys, hop_delay=hop_delay, seed=seed)
        avg_hops = sum(e.hop_count for e in events) / len(events) if events else 0

        results.append({
            "n_nodes": len(ids),
            "avg_hops": round(avg_hops, 3),
            "log2_n": round(math.log2(len(ids)), 3) if len(ids) > 1 else 0,
        })

    return results


import math  # noqa: E402  (needed for scaling_experiment)
