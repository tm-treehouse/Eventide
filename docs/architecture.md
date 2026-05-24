# Architecture notes

## Design philosophy

This is a **functional** model, not cycle-accurate RTL. It captures the
architecturally-visible behaviour of a NIC — the descriptor ring, DMA
movement, packet processing, FIFO occupancy, link serialization, and drops —
at the granularity of discrete events on a nanosecond clock. That is enough to
study the dynamics that matter for architecture and verification: throughput,
latency, backpressure, contention, and where packets are lost.

The structure deliberately mirrors a verification environment:

- Each stage is an independent process with explicit state.
- Stages communicate **only** through `simpy.Store` channels, so there is no
  hidden coupling and backpressure is emergent (a full downstream store blocks
  the upstream `put`).
- The SimPy `Environment` is the single source of time.
- The `Tracer` is a passive observer — it scrapes occupancy and events the way
  a monitor scrapes an interface, and never influences behaviour.

## Pipeline

```
host_tx ─▶ tx_ring ─▶ tx_dma ─▶ proc_in ─▶ proc ─▶ link_in ─▶ link
                         │                                       │
                    (shared DMA engine, capacity = dma_channels) │
host_rx ◀─ host_q ◀─ rx_dma ◀──────────────── rx_in ◀────────────┘
```

## The DMA as a contendable resource

The DMA engine is a `simpy.Resource`. With `capacity=1` it is a single physical
engine shared by the TX and RX datapaths: only one transfer runs at a time and
the other direction queues. That queue **is** the contention you see in the
`dma.busy` signal. Setting `dma_channels=2` gives each direction its own engine
and the contention disappears — a one-line experiment.

## Termination

Service loops (`link`, `host_rx`, `rx_dma`) and the tracer monitors run forever
(`while True`), so the simulation cannot end by "running out of events". Instead
`build_nic` creates a `done` event that fires once every transmitted packet has
been accounted for (delivered to the host or dropped at the MAC), and `run`
calls `env.run(until=done)`. This terminates exactly when the workload is
complete, regardless of the infinite loops.

## Extending the model

- **Logical packet work** lives in `process_packet()` in `blocks.py`. Add header
  parsing, ACL lookups, encryption, or checksum-error injection there.
- **New stages** are just generator functions that `get` from one Store and
  `put` to the next; register them in `build_nic`.
- **New metrics** go in the `stats` dict and/or as `tracer.sample`/`tracer.mark`
  calls, then add a panel in `viz.py`.

## Relationship to SystemC

A SimPy `Store(capacity=n)` is the analog of `sc_fifo<T>(n)`: blocking `put`/`get`
with bounded depth. SimPy's `Environment` + generator processes are the analog of
the SystemC kernel + `SC_THREAD` + `wait()`. The model is therefore a
loosely-timed functional model in the TLM sense — suitable as a golden reference
above RTL, e.g. driven from a cocotb testbench, until simulation throughput or
true RTL co-simulation rigor argues for porting the hot path to C++/SystemC.
