"""Pipeline-stage processes and the packet-processing logic.

Each stage is a generator function (a SimPy process). Stages communicate only
through ``simpy.Store`` channels, so backpressure propagates naturally: a full
downstream store blocks the upstream ``put``.
"""

from __future__ import annotations

import simpy

from nic_sim.core import Dma, Packet, Tracer


def process_packet(pkt: Packet, stats: dict) -> Packet:
    """Pure logical work on a packet (runs in zero simulated time).

    Computes a checksum over the payload, validates it, and classifies the
    packet by size into a coarse traffic class. Extend this with real packet
    logic (header parsing, ACLs, encryption, ...).
    """
    csum = 0
    for b in pkt.payload:
        csum = (csum + b) & 0xFFFF
    pkt.checksum = (~csum) & 0xFFFF

    pkt.csum_ok = pkt.crc_ok  # tie to CRC for the demo

    if pkt.size <= 128:
        pkt.klass = "ctrl"
    elif pkt.size <= 512:
        pkt.klass = "std"
    else:
        pkt.klass = "bulk"

    pkt.offload_done = True
    stats["processed"] = stats.get("processed", 0) + 1
    cc = stats.setdefault("class_counts", {})
    cc[pkt.klass] = cc.get(pkt.klass, 0) + 1
    return pkt


def host_tx(env, tx_ring: simpy.Store, num_packets: int, gap_ns: int, log):
    """Host posts packets (with real payload bytes) into the TX ring."""
    for i in range(1, num_packets + 1):
        size = 1518 if i % 4 == 0 else 64 * ((i % 4) + 1)
        crc = i % 11 != 0
        payload = bytes((i + j) & 0xFF for j in range(min(size, 64)))
        p = Packet(pid=i, size=size, crc_ok=crc, birth=env.now, payload=payload)
        log(env, "HOST_TX", f"post   pid={p.pid} size={p.size}")
        yield tx_ring.put(p)
        yield env.timeout(gap_ns)


def tx_dma_stage(env, tx_ring: simpy.Store, proc_in: simpy.Store, dma: Dma, log):
    """Pull from the ring, DMA the packet into the chip, hand to processing."""
    while True:
        p = yield tx_ring.get()
        yield from dma.transfer(p, "TX")
        log(env, "TX_DMA", f"moved  pid={p.pid} ({p.size}B into chip)")
        yield proc_in.put(p)


def tx_proc_stage(env, proc_in: simpy.Store, link_in: simpy.Store,
                  proc_latency_ns: int, stats: dict, log):
    """The processing stage: do logical work, then forward to the link."""
    while True:
        p = yield proc_in.get()
        process_packet(p, stats)
        yield env.timeout(proc_latency_ns)
        log(env, "PROC", f"done   pid={p.pid} class={p.klass} "
                         f"csum=0x{p.checksum:04x} ok={p.csum_ok}")
        yield link_in.put(p)


def link(env, link_in: simpy.Store, rx_in: simpy.Store, gbps: float,
         stats: dict, tracer: Tracer | None, log):
    """Serialize onto the wire; drop bad-CRC frames at the far-end MAC."""
    bytes_per_ns = (gbps * 1e9 / 8.0) / 1e9
    overhead = 20
    while True:
        p = yield link_in.get()
        yield env.timeout(int((p.size + overhead) / bytes_per_ns))
        log(env, "LINK", f"wire   pid={p.pid}")
        if not p.crc_ok:
            stats["dropped_crc"] = stats.get("dropped_crc", 0) + 1
            if tracer:
                tracer.mark("mac.crc_err", f"pid{p.pid}")
            log(env, "MAC", f"DROP   pid={p.pid} (bad CRC)")
            cb = stats.get("_check_done")
            if cb:
                cb()
            continue
        yield rx_in.put(p)


def rx_dma_stage(env, rx_in: simpy.Store, host_q: simpy.Store, dma: Dma, log):
    """RX side: DMA the received packet up to the host (shares the engine)."""
    while True:
        p = yield rx_in.get()
        yield from dma.transfer(p, "RX")
        log(env, "RX_DMA", f"moved  pid={p.pid} (to host)")
        yield host_q.put(p)


def host_rx(env, host_q: simpy.Store, service_ns: int, stats: dict, log):
    """Host consumes delivered packets."""
    while True:
        p = yield host_q.get()
        yield env.timeout(service_ns)
        stats["received"] = stats.get("received", 0) + 1
        latency = env.now - p.birth
        stats.setdefault("latencies", []).append(latency)
        log(env, "HOST_RX", f"recv   pid={p.pid} class={p.klass} "
                           f"latency={latency} ns")
        cb = stats.get("_check_done")
        if cb:
            cb()
