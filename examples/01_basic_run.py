"""Basic example: run the NIC model with a verbose per-event trace.

    uv run python examples/01_basic_run.py
"""

from nic_sim import run

if __name__ == "__main__":
    result = run(num_packets=12, verbose=True)
    print("\n--- summary ---")
    print(result.summary())
