"""
app.py — Streamlit dashboard for the Chord P2P Simulation.

Tabs
----
1. Ring Topology     – interactive ring diagram, add/remove nodes
2. Finger Table      – inspect finger table of any node
3. Key Lookup        – step-through lookup animation
4. O(log N) Scaling  – experiment showing hop count vs N
"""

import streamlit as st
import random, math, time
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from matplotlib.patches import FancyArrowPatch

from chord import ChordRing, sha1_id
from simulation import run_simulation, scaling_experiment

# ────────────────────────────────────────────────────────────────────────────
# Page config
# ────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Chord DHT Simulator",
    page_icon="🔗",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ────────────────────────────────────────────────────────────────────────────
# Custom CSS
# ────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Syne:wght@400;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Syne', sans-serif;
}
code, pre, .stCode {
    font-family: 'JetBrains Mono', monospace !important;
}

/* Force App Background to Dark */
[data-testid="stAppViewContainer"], [data-testid="stHeader"] {
    background-color: #11111b !important;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background-color: #0d0d14 !important;
    border-right: 1px solid #1e1e2e;
}
[data-testid="stSidebar"] * { color: #cdd6f4 !important; }

/* Main background */
.main .block-container {
    padding: 2rem 3rem;
}

/* Metric cards */
[data-testid="stMetric"] {
    background: #1e1e2e;
    border: 1px solid #313244;
    border-radius: 12px;
    padding: 1rem;
}
[data-testid="stMetricLabel"] { color: #a6adc8 !important; font-size: 0.8rem !important; }
[data-testid="stMetricValue"] { color: #cba6f7 !important; font-size: 1.6rem !important; font-weight: 800 !important; }
[data-testid="stMetricDelta"] { color: #a6e3a1 !important; }

/* Tabs */
[data-baseweb="tab-list"] { background: #1e1e2e; border-radius: 10px; padding: 4px; gap: 4px; }
[data-baseweb="tab"] { border-radius: 8px; color: #a6adc8 !important; font-weight: 600; }
[aria-selected="true"][data-baseweb="tab"] {
    background: #313244 !important;
    color: #cba6f7 !important;
}

/* Buttons */
.stButton > button {
    background: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 8px;
    font-family: 'Syne', sans-serif;
    font-weight: 700;
    transition: all 0.2s;
}
.stButton > button:hover {
    background: #cba6f7;
    color: #1e1e2e;
    border-color: #cba6f7;
}

/* DataFrame */
[data-testid="stDataFrame"] { background: #1e1e2e; border-radius: 12px; }

/* Success / info / warning */
.stAlert { border-radius: 10px; }

/* Title & Text Colors */
h1 { color: #cba6f7 !important; font-weight: 800 !important; letter-spacing: -0.5px; }
h2, h3 { color: #cdd6f4 !important; }
p, li, span, div { color: #a6adc8; } /* Catch all standard text */

/* Number input / select */
[data-baseweb="input"] input, [data-baseweb="select"] { background: #1e1e2e !important; color: #cdd6f4 !important; }
</style>
""", unsafe_allow_html=True)
# ────────────────────────────────────────────────────────────────────────────
# Session state — shared ring
# ────────────────────────────────────────────────────────────────────────────
if "ring" not in st.session_state:
    rng = random.Random(7)
    m = 6
    ring = ChordRing(m=m)
    for nid in sorted(rng.sample(range(2 ** m), 8)):
        ring.add_node(nid)
    st.session_state.ring = ring
    st.session_state.m = m

ring: ChordRing = st.session_state.ring
m: int = st.session_state.m

# ────────────────────────────────────────────────────────────────────────────
# Sidebar controls
# ────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Ring Controls")
    st.markdown(f"**Ring size:** 2^{m} = {2**m} slots")
    st.markdown(f"**Active nodes:** {len(ring.nodes)}")

    st.divider()
    st.markdown("### ➕ Add Node")
    new_id = st.number_input("Node ID", min_value=0, max_value=2**m - 1, step=1, key="add_id")
    if st.button("Add Node"):
        try:
            ring.add_node(int(new_id))
            st.success(f"Node {int(new_id)} added.")
            st.rerun()
        except ValueError as e:
            st.error(str(e))

    st.markdown("### ➖ Remove Node")
    if ring.nodes:
        del_id = st.selectbox("Node ID", options=sorted(ring.nodes.keys()), key="del_id")
        if st.button("Remove Node"):
            try:
                ring.remove_node(del_id)
                st.success(f"Node {del_id} removed.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))

    st.divider()
    if st.button("🔄 Reset to Default Ring"):
        rng = random.Random(7)
        new_ring = ChordRing(m=m)
        for nid in sorted(rng.sample(range(2 ** m), 8)):
            new_ring.add_node(nid)
        st.session_state.ring = new_ring
        ring = new_ring
        st.rerun()

# ────────────────────────────────────────────────────────────────────────────
# Helper: draw ring
# ────────────────────────────────────────────────────────────────────────────
def draw_ring(ring: ChordRing,
              highlight_nodes: list[int] = None,
              highlight_key_id: int = None,
              hops: list[int] = None,
              ax=None,
              title: str = "Chord Ring Topology"):
    if ax is None:
        fig, ax = plt.subplots(figsize=(7, 7), facecolor="#11111b")
    else:
        fig = ax.get_figure()

    ax.set_facecolor("#11111b")
    ax.set_xlim(-1.5, 1.5)
    ax.set_ylim(-1.5, 1.5)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(title, color="#cba6f7", fontsize=13, fontweight="bold", pad=12)

    ring_size = 2 ** ring.m

    # Outer ring circle
    circle = plt.Circle((0, 0), 1.0, color="#313244", fill=False, linewidth=2)
    ax.add_patch(circle)

    def slot_to_xy(slot_id, r=1.0):
        angle = 2 * math.pi * slot_id / ring_size - math.pi / 2
        return r * math.cos(angle), r * math.sin(angle)

    node_ids = sorted(ring.nodes.keys())

    # Draw successor arcs
    for nid in node_ids:
        succ = ring.nodes[nid].successor
        if succ is not None and succ != nid:
            x1, y1 = slot_to_xy(nid)
            x2, y2 = slot_to_xy(succ)
            ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                        arrowprops=dict(arrowstyle="-|>",
                                        color="#45475a",
                                        lw=1.2,
                                        connectionstyle="arc3,rad=0.05"))

    # Draw hop path
    if hops and len(hops) > 1:
        for i in range(len(hops) - 1):
            x1, y1 = slot_to_xy(hops[i], r=0.95)
            x2, y2 = slot_to_xy(hops[i + 1], r=0.95)
            ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                        arrowprops=dict(arrowstyle="-|>",
                                        color="#f38ba8",
                                        lw=2,
                                        connectionstyle="arc3,rad=0.25"))

    # Draw nodes
    for nid in node_ids:
        x, y = slot_to_xy(nid)
        is_hop = hops and nid in hops
        is_start = hops and hops and nid == hops[0]
        is_end = hops and nid == hops[-1]

        if is_start:
            color = "#a6e3a1"
        elif is_end:
            color = "#fab387"
        elif is_hop:
            color = "#f38ba8"
        else:
            color = "#89b4fa"

        circle_node = plt.Circle((x, y), 0.07, color=color, zorder=5)
        ax.add_patch(circle_node)
        # Label
        offset = 0.17
        ax.text(x * (1 + offset / abs(x + 1e-9) * 0.7),
                y * (1 + offset / abs(y + 1e-9) * 0.7),
                str(nid), color="#cdd6f4", fontsize=9,
                ha="center", va="center", fontweight="bold",
                zorder=6)

    # Draw key dot if provided
    if highlight_key_id is not None:
        kx, ky = slot_to_xy(highlight_key_id, r=1.0)
        ax.plot(kx, ky, "D", color="#f9e2af", markersize=9, zorder=7)
        ax.text(kx * 1.22, ky * 1.22, f"k={highlight_key_id}",
                color="#f9e2af", fontsize=8, ha="center")

    # Legend
    legend_items = [
        mpatches.Patch(color="#89b4fa", label="Node"),
        mpatches.Patch(color="#a6e3a1", label="Lookup start"),
        mpatches.Patch(color="#fab387", label="Responsible node"),
        mpatches.Patch(color="#f38ba8", label="Hop path"),
    ]
    ax.legend(handles=legend_items, loc="lower right",
              facecolor="#1e1e2e", edgecolor="#313244",
              labelcolor="#cdd6f4", fontsize=7.5)

    return fig


# ────────────────────────────────────────────────────────────────────────────
# Main header
# ────────────────────────────────────────────────────────────────────────────
st.markdown("# 🔗 Chord DHT Simulator")
st.markdown("A discrete-event simulation of the Chord Peer-to-Peer Lookup Protocol, built with **SimPy** + **Streamlit**.")

col1, col2, col3 = st.columns(3)
col1.metric("Ring Size (2^m)", f"{2**m}", f"m = {m}")
col2.metric("Active Nodes", len(ring.nodes))
col3.metric("Theoretical O(log N)", f"≤ {math.ceil(math.log2(max(len(ring.nodes), 2)))} hops")

st.divider()

# ────────────────────────────────────────────────────────────────────────────
# Tabs
# ────────────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "🌐 Ring Topology",
    "📋 Finger Tables",
    "🔍 Key Lookup Animation",
    "📈 O(log N) Scaling",
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Ring Topology
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.markdown("### Current Ring Topology")
    st.markdown(
        "The circle represents all **2^m ID slots**. "
        "Blue dots are **active nodes**; arrows show successor links."
    )

    col_a, col_b = st.columns([2, 1])

    with col_a:
        fig = draw_ring(ring)
        st.pyplot(fig, use_container_width=True)
        plt.close(fig)

    with col_b:
        st.markdown("#### Node List")
        node_data = ring.node_list()
        df_nodes = pd.DataFrame(node_data)
        st.dataframe(df_nodes, use_container_width=True, height=350)

        st.markdown("#### Quick Stats")
        ids = sorted(ring.nodes.keys())
        if len(ids) >= 2:
            gaps = [(ids[(i+1) % len(ids)] - ids[i]) % (2**m) for i in range(len(ids))]
            st.markdown(f"- **Max gap:** {max(gaps)}")
            st.markdown(f"- **Min gap:** {min(gaps)}")
            st.markdown(f"- **Avg gap:** {sum(gaps)/len(gaps):.1f}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Finger Tables
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("### Finger Table Inspector")
    st.markdown(
        "Each node maintains **m** finger table entries. "
        "Entry k points to the first node ≥ (n + 2^k) mod 2^m."
    )

    if ring.nodes:
        selected_node = st.selectbox("Select node to inspect",
                                     options=sorted(ring.nodes.keys()))
        ft = ring.finger_table(selected_node)
        df_ft = pd.DataFrame(ft)
        df_ft.columns = ["k", "Finger Start", "Next Start", "Points to Node"]

        col_ft1, col_ft2 = st.columns([1, 1])
        with col_ft1:
            st.dataframe(df_ft, use_container_width=True)
            node = ring.nodes[selected_node]
            st.info(
                f"**Node {selected_node}** → "
                f"successor: **{node.successor}**, "
                f"predecessor: **{node.predecessor}**"
            )

        with col_ft2:
            # Visualise finger targets on the ring
            fig2, ax2 = plt.subplots(figsize=(5, 5), facecolor="#11111b")
            finger_targets = [e["node"] for e in ft if e["node"] is not None]
            draw_ring(ring,
                      highlight_nodes=[selected_node] + finger_targets,
                      ax=ax2,
                      title=f"Fingers of Node {selected_node}")

            ring_size = 2 ** m

            def slot_to_xy(slot_id, r=1.0):
                angle = 2 * math.pi * slot_id / ring_size - math.pi / 2
                return r * math.cos(angle), r * math.sin(angle)

            # Draw finger arrows
            for entry in ft:
                if entry["node"] is not None and entry["node"] != selected_node:
                    x1, y1 = slot_to_xy(selected_node, r=0.85)
                    x2, y2 = slot_to_xy(entry["node"], r=0.85)
                    ax2.annotate("", xy=(x2, y2), xytext=(x1, y1),
                                arrowprops=dict(arrowstyle="-|>",
                                                color="#cba6f7",
                                                lw=1,
                                                alpha=0.5,
                                                connectionstyle="arc3,rad=0.15"))
            st.pyplot(fig2, use_container_width=True)
            plt.close(fig2)
    else:
        st.warning("No nodes in ring.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Key Lookup Animation
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown("### Key Lookup — Hop-by-Hop Trace")
    st.markdown(
        "Enter a key, choose a starting node, and watch the lookup "
        "route across the ring step by step."
    )

    col_in1, col_in2, col_in3 = st.columns(3)
    with col_in1:
        lookup_key = st.text_input("Key to look up", value="hello_world")
    with col_in2:
        start_options = sorted(ring.nodes.keys())
        if start_options:
            start_node = st.selectbox("Start node", options=start_options)
        else:
            start_node = None
    with col_in3:
        animate = st.checkbox("Animate hops", value=True)

    if st.button("🔍 Run Lookup", use_container_width=True):
        if not ring.nodes:
            st.error("No nodes in ring!")
        else:
            result = ring.lookup(lookup_key, start_node)
            hops = result["hops"]
            key_id = result["key_id"]

            # Summary metrics
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Key", lookup_key)
            c2.metric("Key ID (hash mod 2^m)", key_id)
            c3.metric("Responsible Node", result["responsible"])
            c4.metric("Hops", result["hop_count"])

            st.markdown("---")
            hop_placeholder = st.empty()

            if animate and len(hops) > 1:
                for step in range(1, len(hops) + 1):
                    partial_hops = hops[:step]
                    fig3, ax3 = plt.subplots(figsize=(6, 6), facecolor="#11111b")
                    draw_ring(ring,
                              highlight_key_id=key_id,
                              hops=partial_hops,
                              ax=ax3,
                              title=f"Hop {step - 1}/{result['hop_count']}  —  current: {partial_hops[-1]}")
                    with hop_placeholder.container():
                        st.pyplot(fig3, use_container_width=True)
                    plt.close(fig3)
                    time.sleep(0.6)
            else:
                fig3, ax3 = plt.subplots(figsize=(6, 6), facecolor="#11111b")
                draw_ring(ring,
                          highlight_key_id=key_id,
                          hops=hops,
                          ax=ax3,
                          title=f"Full lookup path ({result['hop_count']} hops)")
                with hop_placeholder.container():
                    st.pyplot(fig3, use_container_width=True)
                plt.close(fig3)

            # Hop trace table
            st.markdown("#### Hop Trace")
            trace_data = []
            for i, hop in enumerate(hops):
                role = "Start" if i == 0 else ("Responsible" if i == len(hops) - 1 else "Intermediate")
                trace_data.append({"Step": i, "Node ID": hop, "Role": role})
            st.dataframe(pd.DataFrame(trace_data), use_container_width=True)

    # ---- SimPy batch simulation ----
    st.markdown("---")
    st.markdown("### SimPy Batch Simulation")
    st.markdown("Run multiple concurrent lookups using the discrete-event engine.")

    col_s1, col_s2, col_s3 = st.columns(3)
    with col_s1:
        num_keys = st.slider("Number of keys", 5, 100, 20)
    with col_s2:
        hop_delay = st.slider("Hop delay (ms)", 5, 50, 10)
    with col_s3:
        sim_seed = st.number_input("Random seed", 1, 9999, 42)

    if st.button("▶️ Run SimPy Simulation", use_container_width=True):
        keys = [f"key_{i}" for i in range(num_keys)]
        events = run_simulation(ring, keys,
                                hop_delay=hop_delay,
                                seed=int(sim_seed))
        df_events = pd.DataFrame([{
            "ID": e.lookup_id,
            "Key": e.key,
            "Key ID": e.key_id,
            "Start Node": e.start_node,
            "Responsible Node": e.responsible,
            "Hops": e.hop_count,
            "Latency (ms)": e.latency_ms,
        } for e in events])

        st.success(f"Simulated {len(events)} lookups.")

        m1, m2, m3 = st.columns(3)
        m1.metric("Avg Hops", f"{df_events['Hops'].mean():.2f}")
        m2.metric("Avg Latency (ms)", f"{df_events['Latency (ms)'].mean():.1f}")
        m3.metric("Max Hops", int(df_events['Hops'].max()))

        fig_hist, ax_hist = plt.subplots(figsize=(8, 3), facecolor="#11111b")
        ax_hist.set_facecolor("#1e1e2e")
        ax_hist.hist(df_events["Hops"], bins=range(0, m + 2),
                     color="#cba6f7", edgecolor="#313244", alpha=0.85)
        ax_hist.set_xlabel("Hop Count", color="#a6adc8")
        ax_hist.set_ylabel("Frequency", color="#a6adc8")
        ax_hist.set_title("Hop Count Distribution", color="#cba6f7", fontweight="bold")
        ax_hist.tick_params(colors="#a6adc8")
        for spine in ax_hist.spines.values():
            spine.set_edgecolor("#313244")
        st.pyplot(fig_hist, use_container_width=True)
        plt.close(fig_hist)

        st.dataframe(df_events, use_container_width=True, height=250)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — O(log N) Scaling
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.markdown("### O(log N) Scaling Experiment")
    st.markdown(
        "As the number of nodes **N** grows, Chord guarantees lookup in "
        "**O(log N)** hops. This experiment confirms that empirically."
    )

    col_e1, col_e2, col_e3 = st.columns(3)
    with col_e1:
        exp_m = st.slider("Ring bits (m)", 4, 8, 6)
    with col_e2:
        exp_lookups = st.slider("Lookups per size", 20, 200, 50)
    with col_e3:
        exp_seed = st.number_input("Seed", 1, 9999, 42, key="exp_seed")

    node_counts = [2, 4, 8, 12, 16, 24, 32, 48, 64]
    node_counts = [n for n in node_counts if n <= 2 ** exp_m]

    if st.button("🧪 Run Scaling Experiment", use_container_width=True):
        with st.spinner("Running experiment across multiple ring sizes…"):
            data = scaling_experiment(
                m=exp_m,
                node_counts=node_counts,
                lookups_per_size=exp_lookups,
                seed=int(exp_seed),
            )

        df_scale = pd.DataFrame(data)
        st.dataframe(df_scale.rename(columns={
            "n_nodes": "N (nodes)",
            "avg_hops": "Avg Hops (empirical)",
            "log2_n": "log₂(N) (theoretical)",
        }), use_container_width=True)

        fig_scale, ax_scale = plt.subplots(figsize=(9, 4), facecolor="#11111b")
        ax_scale.set_facecolor("#1e1e2e")

        ax_scale.plot(df_scale["n_nodes"], df_scale["avg_hops"],
                      "o-", color="#cba6f7", lw=2.5, markersize=7, label="Empirical avg hops")
        ax_scale.plot(df_scale["n_nodes"], df_scale["log2_n"],
                      "s--", color="#a6e3a1", lw=2, markersize=5, alpha=0.85, label="log₂(N)")

        ax_scale.set_xlabel("Number of Nodes (N)", color="#a6adc8", fontsize=11)
        ax_scale.set_ylabel("Hops", color="#a6adc8", fontsize=11)
        ax_scale.set_title("Chord Lookup Hops vs Ring Size", color="#cba6f7",
                           fontsize=13, fontweight="bold")
        ax_scale.legend(facecolor="#313244", edgecolor="#45475a", labelcolor="#cdd6f4")
        ax_scale.tick_params(colors="#a6adc8")
        for spine in ax_scale.spines.values():
            spine.set_edgecolor("#313244")
        ax_scale.grid(True, color="#313244", linestyle="--", alpha=0.5)

        st.pyplot(fig_scale, use_container_width=True)
        plt.close(fig_scale)

        st.success(
            "✅ As N doubles, average hops increase by ~1, confirming **O(log N)** complexity."
        )
