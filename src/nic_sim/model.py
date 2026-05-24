"""Assembles the pipeline blocks into a NIC and provides the run entry point."""

from __future__ import annotations

import statistics
from dataclasses import dataclass

import simpy

from nic_sim import blocks
from nic_sim.core import Dma, Tracer


@dataclass
class NicConfig:
    """All tunable knobs for a run. Edit these to explore the design space."""

    num_packets: int = 12
    host_tx_gap_ns: int = 200
    host_rx_svc_ns: int = 400
    link_gbps: float = 1.0
    dma_gbps: float = 4.0
    dma_channels: int = 1          # 1 = shared TX/RX engine (contention)
    proc_latency_ns: int = 150
    ring_depth: int = 8
    stage_depth: int = 4
    trace: bool = True
    trace_period_ns: int = 50
    verbose: bool = False


@dataclass
class RunResult:
    """Everything a run produces: aggregate stats, the tracer, and config."""

    stats: dict
    tracer: Tracer | None
    config: NicConfig
    end_time: int

    def summary(self) -> str:
        s = self.stats
        lat = s.get("latencies", [])
        lines = [
            f"processed     : {s.get('processed', 0)}",
            f"classes       : {s.get('class_counts', {})}",
            f"DMA transfers : {s.get('dma_xfers', 0)} "
            f"({s.get('dma_bytes', 0):,} bytes)",
            f"CRC drops     : {s.get('dropped_crc', 0)}",
            f"host received : {s.get('received', 0)}",
        ]
        if lat:
            lines.append(
                f"latency ns    : min={min(lat)} "
                f"mean={statistics.mean(lat):.0f} max={max(lat)}"
            )
        return "\n".join(lines)


def _make_logger(verbose: bool):
    if verbose:
        def log(env, tag, msg):
            print(f"[{env.now:6d} ns] {tag:8s} {msg}")
    else:
        def log(env, tag, msg):
            pass
    return log


def build_nic(env: simpy.Environment, cfg: NicConfig):
    """Wire up all stages and return (stats, tracer, done). ``done`` is an
    event that fires once every transmitted packet has been either delivered
    to the host or dropped at the MAC. Run with ``env.run(until=done)`` so the
    simulation stops cleanly despite the infinite service/monitor loops.
    """
    log = _make_logger(cfg.verbose)
    tracer = Tracer(env) if cfg.trace else None

    stats: dict = {
        "dropped_crc": 0, "received": 0, "processed": 0,
        "dma_bytes": 0, "dma_xfers": 0,
    }

    done = env.event()

    def check_done(_value=None):
        accounted = stats["received"] + stats["dropped_crc"]
        if accounted >= cfg.num_packets and not done.triggered:
            done.succeed()

    stats["_check_done"] = check_done

    dma_bytes_per_ns = (cfg.dma_gbps * 1e9 / 8.0) / 1e9
    dma = Dma(env, "dma", dma_bytes_per_ns, channels=cfg.dma_channels,
              tracer=tracer, stats=stats)

    tx_ring = simpy.Store(env, capacity=cfg.ring_depth)
    proc_in = simpy.Store(env, capacity=cfg.stage_depth)
    link_in = simpy.Store(env, capacity=cfg.stage_depth)
    rx_in = simpy.Store(env, capacity=cfg.stage_depth)
    host_q = simpy.Store(env, capacity=cfg.ring_depth)

    env.process(blocks.host_tx(env, tx_ring, cfg.num_packets,
                               cfg.host_tx_gap_ns, log))
    env.process(blocks.tx_dma_stage(env, tx_ring, proc_in, dma, log))
    env.process(blocks.tx_proc_stage(env, proc_in, link_in,
                                     cfg.proc_latency_ns, stats, log))
    env.process(blocks.link(env, link_in, rx_in, cfg.link_gbps,
                            stats, tracer, log))
    env.process(blocks.rx_dma_stage(env, rx_in, host_q, dma, log))
    env.process(blocks.host_rx(env, host_q, cfg.host_rx_svc_ns, stats, log))

    if tracer:
        for nm, st in [("tx_ring", tx_ring), ("proc_in", proc_in),
                       ("link_in", link_in), ("rx_in", rx_in),
                       ("host_q", host_q)]:
            env.process(tracer.monitor_store(nm, st, cfg.trace_period_ns))

    return stats, tracer, done


def run(config: NicConfig | None = None, **overrides) -> RunResult:
    """Build and run a NIC simulation. Pass a ``NicConfig`` or keyword
    overrides (e.g. ``run(num_packets=500, dma_channels=2)``)."""
    cfg = config or NicConfig()
    for k, v in overrides.items():
        if not hasattr(cfg, k):
            raise TypeError(f"unknown config field: {k}")
        setattr(cfg, k, v)

    env = simpy.Environment()
    stats, tracer, done = build_nic(env, cfg)
    env.run(until=done)
    stats.pop("_check_done", None)
    return RunResult(stats=stats, tracer=tracer, config=cfg, end_time=env.now)
