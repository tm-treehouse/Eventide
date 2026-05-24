"""Parameter sweep: vary DMA bandwidth and observe mean latency.

Shows the pattern you'd use for architectural exploration -- run the model
across a range of a knob and tabulate a metric.

    uv run python examples/03_sweep.py
"""

import statistics

from nic_sim import run

if __name__ == "__main__":
    print(f"{'DMA GB/s':>9} | {'mean latency (ns)':>18} | {'end time (ns)':>13}")
    print("-" * 48)
    for dma_gbps in (1.0, 2.0, 4.0, 8.0, 16.0):
        result = run(num_packets=100, dma_gbps=dma_gbps, trace=False)
        lat = result.stats["latencies"]
        mean_lat = statistics.mean(lat) if lat else float("nan")
        print(f"{dma_gbps:>9.1f} | {mean_lat:>18.0f} | {result.end_time:>13,}")
