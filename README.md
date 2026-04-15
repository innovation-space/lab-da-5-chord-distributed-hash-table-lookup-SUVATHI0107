# Chord DHT Simulator

A discrete-event simulation of the **Chord Peer-to-Peer Lookup Protocol** built with **SimPy** and **Streamlit**.

---

## Overview

Chord is a scalable, decentralised lookup protocol for distributed hash tables (DHTs).  
Given a key, any node in the ring can find the node responsible for storing that key in **O(log N)** messages, where N is the number of nodes.

This simulator models:

| Feature | Details |
|---|---|
| Consistent hashing | SHA-1 digests mapped to M-bit identifiers |
| Finger tables | Each node keeps M pointers for O(log N) routing |
| Successor / predecessor | Maintained per node, updated on join/departure |
| Key lookup | Iterative hop-by-hop routing traced visually |
| Node join / departure | Add or remove nodes; ring auto-rebuilds |
| SimPy simulation | Concurrent lookups with configurable per-hop latency |
| O(log N) scaling | Empirical experiment confirming theoretical bound |

---

## Project Structure

```
chord_sim/
├── chord.py          # Core Chord protocol (hashing, finger tables, lookup)
├── simulation.py     # SimPy discrete-event simulation engine
├── app.py            # Streamlit dashboard (4 tabs)
├── requirements.txt  # Python dependencies
└── README.md         # This file
```

---

## Installation & Running

```bash
# 1. Clone / download the project
git clone <your-repo-url>
cd chord_sim

# 2. Install dependencies
pip install -r requirements.txt

# 3. Launch the Streamlit app
streamlit run app.py
```

The dashboard opens at `http://localhost:8501`.

---

## Module Descriptions

### `chord.py` — Core Protocol Logic

#### `sha1_id(key, m)`
Hashes any string to an M-bit Chord identifier using SHA-1.

```python
sha1_id("hello", m=6)   # → some int in [0, 64)
```

#### `in_range(x, a, b, m)`
Tests whether `x` lies in the **circular interval** `(a, b]` on a 2^m ring, correctly handling wrap-around.

#### `ChordNode`
Represents a single node:

| Attribute | Description |
|---|---|
| `id` | Node's M-bit identifier |
| `finger[k]` | Finger table — `m` entries |
| `successor` | Next node clockwise |
| `predecessor` | Previous node clockwise |
| `find_successor_local(key_id, ring)` | Iterative lookup returning `(responsible, [hops])` |
| `_closest_preceding_finger(key_id)` | Core routing step — finds the finger closest to key without overshooting |

#### `ChordRing`
Manages the full ring:

| Method | Description |
|---|---|
| `add_node(id)` | Insert node, rebuild ring |
| `remove_node(id)` | Remove node, rebuild ring |
| `lookup(key, start)` | Full lookup returning hop trace dict |
| `finger_table(node_id)` | Returns finger table as list of dicts |
| `node_list()` | Returns all nodes with successor/predecessor |

---

### `simulation.py` — SimPy Engine

#### `lookup_process(env, ring, key, start, id, results, hop_delay)`
A SimPy **process** that:
1. Calls `ring.lookup()` to compute the hop path
2. Simulates each hop with `env.timeout(hop_delay)`
3. Records a `LookupEvent` with arrival/completion times and latency

#### `run_simulation(ring, keys, hop_delay, inter_arrival, seed)`
Runs a batch of concurrent lookups:
- Keys arrive with **Poisson** inter-arrival times
- Each is assigned a random start node
- Returns a list of `LookupEvent` objects

#### `scaling_experiment(m, node_counts, lookups_per_size, hop_delay, seed)`
Sweeps N from small to large, measuring average hop count.  
Used by the O(log N) tab to generate the scaling chart.

---

## Streamlit Dashboard — Tabs

### 🌐 Ring Topology
- Circular ring diagram with all active nodes
- Successor arrows between consecutive nodes
- Node table (ID, successor, predecessor)
- Gap statistics (min/max/avg distance between nodes)

### 📋 Finger Tables
- Select any node to inspect its M finger entries
- Each entry shows: k, finger start, interval end, target node
- Ring diagram with finger arrows overlaid in purple

### 🔍 Key Lookup Animation
- Enter any string key and a start node
- **Animated hop-by-hop** trace on the ring (configurable)
- Summary metrics: key ID, responsible node, hop count
- Hop trace table with node roles
- **SimPy batch simulation**: run N concurrent lookups and see hop distribution histogram

### 📈 O(log N) Scaling
- Configurable ring size (m), lookups per size, random seed
- Plots empirical average hops vs. theoretical log₂(N)
- Confirms the O(log N) guarantee

---

## Chord Protocol — Key Concepts

### Consistent Hashing
Both nodes and keys are assigned IDs in [0, 2^m). The node responsible for key `k` is the first node with ID ≥ k (clockwise), called the **successor** of k.

### Finger Table
Node n's k-th finger points to:
```
finger[k] = successor( (n + 2^k) mod 2^m )   for k = 0..m-1
```
This gives each node O(log N) pointers that double in distance, enabling O(log N) routing.

### Lookup Algorithm (Iterative)
```
find_successor(key_id):
  if key_id in (current, current.successor]:
      return current.successor
  else:
      next = closest_preceding_finger(key_id)
      forward to next and repeat
```

### Complexity
| Operation | Messages |
|---|---|
| Key lookup | O(log N) |
| Node join | O(log² N) |
| Node departure | O(log² N) |

---

## Example Output

Running the O(log N) scaling experiment (m=6, 50 lookups each):

| N (nodes) | Avg Hops | log₂(N) |
|---|---|---|
| 2 | 0.98 | 1.00 |
| 4 | 1.54 | 2.00 |
| 8 | 2.32 | 3.00 |
| 16 | 3.06 | 4.00 |
| 32 | 3.84 | 5.00 |
| 64 | 4.72 | 6.00 |

Average hops ≈ log₂(N), confirming the O(log N) guarantee.

