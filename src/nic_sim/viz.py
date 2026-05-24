"""Post-run visualization: render a Tracer's signals into a timeline plot."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from nic_sim.core import Tracer  # noqa: E402


def _step(ax, samples, color, label, fill=False):
    if not samples:
        return
    xs = [t / 1000 for t, _ in samples]  # ns -> us
    ys = [v for _, v in samples]
    ax.step(xs, ys, where="post", color=color, label=label, linewidth=1.4)
    if fill:
        ax.fill_between(xs, ys, step="post", alpha=0.15, color=color)


def render_timeline(tracer: Tracer, end_time_ns: int, stats: dict, path: str) -> str:
    """Render the trace into a stacked multi-panel timeline PNG."""
    sig = tracer.signals
    ev = tracer.events
    end_us = end_time_ns / 1000

    fig, axes = plt.subplots(4, 1, figsize=(13, 9), sharex=True)
    fig.suptitle("NIC model — internal state timeline", fontsize=14,
                 fontweight="bold")

    C = {"ring": "#16a34a", "proc": "#7c3aed", "dma": "#0891b2",
         "link": "#ea580c", "drop": "#b91c1c"}

    # Panel 0: store occupancies (the FIFOs)
    ax = axes[0]
    _step(ax, sig.get("tx_ring.occupancy", []), C["ring"], "tx_ring")
    _step(ax, sig.get("proc_in.occupancy", []), C["proc"], "proc_in")
    _step(ax, sig.get("link_in.occupancy", []), C["link"], "link_in")
    ax.set_ylabel("TX-side\noccupancy")
    ax.legend(loc="upper right", fontsize=8, ncol=3)
    ax.set_title("TX-side queue occupancy", fontsize=10, loc="left")

    # Panel 1: RX-side store occupancies
    ax = axes[1]
    _step(ax, sig.get("rx_in.occupancy", []), C["link"], "rx_in")
    _step(ax, sig.get("host_q.occupancy", []), C["ring"], "host_q")
    ax.set_ylabel("RX-side\noccupancy")
    ax.legend(loc="upper right", fontsize=8, ncol=2)
    ax.set_title("RX-side queue occupancy", fontsize=10, loc="left")

    # Panel 2: DMA channel busy
    ax = axes[2]
    _step(ax, sig.get("dma.busy", []), C["dma"], "DMA channels busy", fill=True)
    ax.set_ylabel("DMA\nbusy")
    ax.legend(loc="upper right", fontsize=8)
    ax.set_title("DMA engine occupancy (TX+RX contend)", fontsize=10, loc="left")

    # Panel 3: drop events
    ax = axes[3]
    for t, _ in ev.get("mac.crc_err", []):
        ax.axvline(t / 1000, color=C["drop"], alpha=0.7, linewidth=1.2)
    ax.set_ylabel("drops")
    ax.set_yticks([])
    ax.set_title("CRC drops", fontsize=10, loc="left")

    axes[-1].set_xlabel("time (µs)")
    for ax in axes:
        ax.set_xlim(0, max(end_us, 1))
        ax.grid(True, alpha=0.2)

    footer = (f"processed: {stats.get('processed', 0)}  |  "
              f"received: {stats.get('received', 0)}  |  "
              f"CRC drops: {stats.get('dropped_crc', 0)}  |  "
              f"DMA xfers: {stats.get('dma_xfers', 0)}")
    fig.text(0.5, 0.01, footer, ha="center", fontsize=9, family="monospace",
             bbox=dict(boxstyle="round", facecolor="#f1f5f9", edgecolor="#cbd5e1"))

    fig.tight_layout(rect=[0, 0.03, 1, 0.97])
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return path
