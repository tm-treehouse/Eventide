"""Core building blocks shared across the model: the Packet transaction,
the DMA engine, and the Tracer that records internal state for analysis.
"""

from __future__ import annotations

from dataclasses import dataclass

import simpy

# Time unit: integers in nanoseconds.
NS = 1


@dataclass
class Packet:
    """A packet transaction flowing through the NIC pipeline.

    The first group of fields is set by the producer (host or wire); the
    second group is filled in by the processing stage.
    """

    pid: int
    size: int
    crc_ok: bool = True
    birth: int = 0
    payload: bytes = b""

    # filled in by the processing stage
    checksum: int = 0
    csum_ok: bool = True
    klass: str = "?"
    offload_done: bool = False


class Dma:
    """A DMA engine backed by a ``simpy.Resource``.

    ``channels=1`` models a single physical engine: only one transfer runs at
    a time and concurrent requesters queue (that queue is the contention).
    Transfer duration is ``size / bytes_per_ns``.
    """

    def __init__(
        self,
        env: simpy.Environment,
        name: str,
        bytes_per_ns: float,
        channels: int = 1,
        tracer: Tracer | None = None,
        stats: dict | None = None,
    ):
        self.env = env
        self.name = name
        self.bytes_per_ns = bytes_per_ns
        self.resource = simpy.Resource(env, capacity=channels)
        self.tracer = tracer
        self.stats = stats

    def transfer(self, pkt: Packet, who: str = ""):
        """Generator: acquire a channel, move the bytes, release.

        Use as ``yield from dma.transfer(pkt, "TX")`` inside a process.
        """
        req = self.resource.request()
        yield req
        if self.tracer is not None:
            self.tracer.sample(f"{self.name}.busy", len(self.resource.users))
        dur = max(int(pkt.size / self.bytes_per_ns), 1)
        if self.stats is not None:
            self.stats["dma_bytes"] = self.stats.get("dma_bytes", 0) + pkt.size
            self.stats["dma_xfers"] = self.stats.get("dma_xfers", 0) + 1
        yield self.env.timeout(dur)
        self.resource.release(req)
        if self.tracer is not None:
            self.tracer.sample(f"{self.name}.busy", len(self.resource.users))


class Tracer:
    """Passive observer of internal state.

    ``sample`` records a ``(time, value)`` point on a named signal (think of a
    waveform); ``mark`` records a point event (a drop, a completion).
    """

    def __init__(self, env: simpy.Environment):
        self.env = env
        self.signals: dict[str, list[tuple[int, float]]] = {}
        self.events: dict[str, list[tuple[int, str]]] = {}

    def sample(self, signal: str, value: float) -> None:
        self.signals.setdefault(signal, []).append((self.env.now, value))

    def mark(self, channel: str, label: str = "") -> None:
        self.events.setdefault(channel, []).append((self.env.now, label))

    def monitor_store(self, name: str, store: simpy.Store, period_ns: int = 50):
        """A process that samples a Store's occupancy at a fixed period, so
        FIFO fill levels show up as signals in the trace."""

        def proc():
            while True:
                self.sample(f"{name}.occupancy", len(store.items))
                yield self.env.timeout(period_ns)

        return proc()
