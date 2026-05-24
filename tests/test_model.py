"""Tests for the NIC model. Run with: uv run pytest"""

from __future__ import annotations

from nic_sim import Packet, run
from nic_sim.blocks import process_packet


def test_run_basic_completes():
    result = run(num_packets=12)
    # 12 posted, 1 is bad-CRC (pid 11) and dropped at MAC, so 11 delivered.
    assert result.stats["processed"] == 12
    assert result.stats["received"] == 11
    assert result.stats["dropped_crc"] == 1


def test_determinism():
    a = run(num_packets=50)
    b = run(num_packets=50)
    assert a.stats["received"] == b.stats["received"]
    assert a.stats["latencies"] == b.stats["latencies"]


def test_scaling_packet_count():
    for n in (1, 10, 100):
        result = run(num_packets=n)
        # number bad-CRC = multiples of 11 in [1, n]
        bad = n // 11
        assert result.stats["received"] == n - bad


def test_dma_channels_affect_timing():
    """A second DMA channel removes TX/RX contention, so the run finishes no
    later (and generally sooner) than with a single shared channel."""
    shared = run(num_packets=40, dma_channels=1)
    split = run(num_packets=40, dma_channels=2)
    assert split.end_time <= shared.end_time


def test_dma_transfer_count():
    """Each delivered packet is DMA'd twice (TX in, RX out); dropped packets
    only get the TX transfer."""
    result = run(num_packets=12)
    # 12 TX transfers + 11 RX transfers (pid 11 dropped before RX DMA)
    assert result.stats["dma_xfers"] == 12 + 11


def test_process_packet_classification():
    stats: dict = {}
    small = process_packet(Packet(pid=1, size=64, payload=b"\x01\x02"), stats)
    mid = process_packet(Packet(pid=2, size=256, payload=b"\x01"), stats)
    big = process_packet(Packet(pid=3, size=1518, payload=b"\xff"), stats)
    assert small.klass == "ctrl"
    assert mid.klass == "std"
    assert big.klass == "bulk"
    assert small.offload_done


def test_process_packet_checksum_deterministic():
    stats: dict = {}
    p1 = process_packet(Packet(pid=1, size=64, payload=b"abc"), stats)
    p2 = process_packet(Packet(pid=2, size=64, payload=b"abc"), dict())
    assert p1.checksum == p2.checksum


def test_config_override_rejects_unknown():
    import pytest

    with pytest.raises(TypeError):
        run(not_a_real_field=123)


def test_tracer_collects_signals():
    result = run(num_packets=20, trace=True)
    assert result.tracer is not None
    # the DMA busy signal and at least one store occupancy should be present
    assert "dma.busy" in result.tracer.signals
    assert any(k.endswith(".occupancy") for k in result.tracer.signals)
