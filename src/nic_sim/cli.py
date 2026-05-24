"""Command-line interface: ``nic-sim`` runs a simulation and optionally plots."""

from __future__ import annotations

import argparse

from nic_sim.model import NicConfig, run


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="nic-sim",
        description="Run the system-level NIC functional model.",
    )
    p.add_argument("-n", "--num-packets", type=int, default=12)
    p.add_argument("--dma-gbps", type=float, default=4.0)
    p.add_argument("--dma-channels", type=int, default=1,
                   help="1 = shared TX/RX engine (contention); 2 = separate")
    p.add_argument("--proc-latency-ns", type=int, default=150)
    p.add_argument("--link-gbps", type=float, default=1.0)
    p.add_argument("-v", "--verbose", action="store_true",
                   help="print per-event trace")
    p.add_argument("--plot", metavar="PATH",
                   help="render a timeline PNG to PATH")
    args = p.parse_args(argv)

    cfg = NicConfig(
        num_packets=args.num_packets,
        dma_gbps=args.dma_gbps,
        dma_channels=args.dma_channels,
        proc_latency_ns=args.proc_latency_ns,
        link_gbps=args.link_gbps,
        verbose=args.verbose,
        trace=bool(args.plot) or args.verbose,
    )
    result = run(cfg)
    print(result.summary())

    if args.plot:
        if result.tracer is None:
            print("warning: tracing was disabled; cannot plot")
        else:
            from nic_sim.viz import render_timeline

            out = render_timeline(result.tracer, result.end_time,
                                  result.stats, args.plot)
            print(f"timeline written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
