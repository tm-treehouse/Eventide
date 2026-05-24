# nic-sim

A system-level **functional model of a network interface card (NIC)**, built on
[SimPy](https://simpy.readthedocs.io/). It models the NIC datapath as a pipeline
of composable stages — host → DMA → packet processing → link → DMA → host —
records internal state during the run, and renders a post-run timeline for
analysis.

It's meant for **architectural exploration and verification reference modeling**:
size the FIFOs, study DMA contention, measure latency under load, and use it as a
golden reference alongside RTL (e.g. driven from a [cocotb](https://www.cocotb.org/)
testbench).

## Why SimPy

SimPy provides the discrete-event kernel and bounded blocking channels
(`simpy.Store`) that a hardware model needs — the same role `sc_fifo` and the
kernel play in SystemC, but with Python's iteration speed and analysis ecosystem.
Backpressure is emergent: a full downstream stage blocks the upstream `put`, so
stalls ripple back through the pipeline the way they do in real hardware.

## Install

This project uses [uv](https://docs.astral.sh/uv/).

```bash
# create the environment and install the package + dev tools
uv sync --extra dev

# run the test suite
uv run pytest

# run the CLI
uv run nic-sim --num-packets 40 --verbose
uv run nic-sim --num-packets 40 --plot timeline.png
```

## Usage as a library

```python
from nic_sim import run

# single run with keyword overrides
result = run(num_packets=200, dma_channels=2, dma_gbps=8.0)
print(result.summary())

# the trace is available for custom analysis / plotting
from nic_sim.viz import render_timeline
render_timeline(result.tracer, result.end_time, result.stats, "out.png")
```

Or build it explicitly for finer control:

```python
import simpy
from nic_sim import NicConfig, build_nic

env = simpy.Environment()
stats, tracer = build_nic(env, NicConfig(num_packets=500))
env.run()
```

## Architecture

```
host_tx ─▶ tx_ring ─▶ tx_dma ─▶ proc_in ─▶ proc ─▶ link_in ─▶ link
                         │                                       │
                    (shared DMA engine)                          ▼
host_rx ◀─ host_q ◀─ rx_dma ◀──────────────── rx_in ◀────────────┘
```

- **`core.py`** — `Packet`, the `Dma` engine (a `simpy.Resource`, so transfers
  contend for the channel), and the `Tracer`.
- **`blocks.py`** — the pipeline-stage processes and `process_packet()`, the hook
  for logical work (checksum, classification — extend with real packet logic).
- **`model.py`** — `NicConfig`, `build_nic()`, and the `run()` entry point.
- **`viz.py`** — `render_timeline()` for the multi-panel state plot.
- **`cli.py`** — the `nic-sim` console command.

## Key knobs (`NicConfig`)

| field | meaning |
|---|---|
| `num_packets` | how many packets the host transmits |
| `dma_gbps` | DMA engine bandwidth |
| `dma_channels` | `1` = shared TX/RX engine (contention); `2` = separate |
| `proc_latency_ns` | time the processing stage adds per packet |
| `link_gbps` | wire line rate |
| `ring_depth` / `stage_depth` | channel capacities (where backpressure forms) |

## Examples

```bash
uv run python examples/01_basic_run.py        # verbose trace
uv run python examples/02_dma_contention.py   # shared vs split DMA, with plots
uv run python examples/03_sweep.py            # latency vs DMA bandwidth sweep
```

## License

MIT — see [LICENSE](LICENSE).
