"""DMA contention experiment: compare a shared DMA engine (1 channel) against
separate TX/RX engines (2 channels), and render a timeline for each.

    uv run python examples/02_dma_contention.py
"""

from nic_sim import run
from nic_sim.viz import render_timeline

if __name__ == "__main__":
    for channels in (1, 2):
        result = run(num_packets=40, dma_channels=channels, dma_gbps=4.0)
        label = "shared" if channels == 1 else "split"
        print(f"=== DMA {channels} channel(s) ({label}) ===")
        print(result.summary())
        out = render_timeline(
            result.tracer, result.end_time, result.stats,
            f"timeline_dma_{label}.png",
        )
        print(f"  plot: {out}\n")
