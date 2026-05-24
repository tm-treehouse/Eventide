"""nic_sim: a system-level functional model of a network interface card.

Built on SimPy. Provides composable pipeline blocks (DMA, processing, link),
a packet type, internal-state tracing, and post-run visualization.

Quick start
-----------
    from nic_sim import build_nic, run

    result = run(num_packets=200)
    print(result.stats)
"""

from nic_sim.core import Dma, Packet, Tracer
from nic_sim.model import NicConfig, RunResult, build_nic, run

__version__ = "0.1.0"

__all__ = [
    "Packet",
    "Dma",
    "Tracer",
    "NicConfig",
    "build_nic",
    "run",
    "RunResult",
]
