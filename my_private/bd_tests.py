"""Quick harness to exercise the UNS path normaliser helpers.

Run manually (python my_private/bd_tests.py) to inspect the device and
metric paths calculated from the golden Sparkplug DBIRTH sample. This script is
intentionally lightweight and not part of the automated test suite; it is handy
when iterating on path_normalizer.py.

Author: UNS Team
Date: 2025-10-01
"""

from __future__ import annotations

import json
from pathlib import Path

from uns_metadata_sync.path_normalizer import (
    metric_path_to_canary_id,
    normalize_device_path,
    normalize_metric_path,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = (
    PROJECT_ROOT
    / "tests"
    / "fixtures"
    / "messages_spBv1.0_Secil_DBIRTH_Portugal_Cement.json"
)

# Representative context mirroring the sample fixture. In live processing these
# values originate from the MQTT topic: spBv1.0/<group>/<msgType>/<edge>/<device>.
GROUP = "Secil"
EDGE_NODE = "Maceira-Ignition-Edge"
DEVICE = "Kiln-K1"


def exercise_normaliser() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    device_path = normalize_device_path(
        group=GROUP,
        edge_node=EDGE_NODE,
        device=DEVICE,
    )
    print(f"Device path: {device_path}")

    for metric in payload.get("metrics", []):
        metric_name = metric.get("name", "")
        if not metric_name:
            continue

        metric_path = normalize_metric_path(
            group=GROUP,
            edge_node=EDGE_NODE,
            device=DEVICE,
            metric_name=metric_name,
        )
        canary_id = metric_path_to_canary_id(metric_path)

        print("-" * 80)
        print(f"Metric name  : {metric_name}")
        print(f"UNS path     : {metric_path}")
        print(f"Canary tag id: {canary_id}")


if __name__ == "__main__":
    exercise_normaliser()
