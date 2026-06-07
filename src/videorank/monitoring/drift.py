from __future__ import annotations

import argparse
import json
from pathlib import Path

from videorank.model.metrics import population_stability_index


def load_scores(path: Path, field: str = "score") -> list[float]:
    scores: list[float] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            payload = json.loads(line)
            if field in payload:
                scores.append(float(payload[field]))
                continue
            for recommendation in payload.get("recommendations", []):
                if field in recommendation:
                    scores.append(float(recommendation[field]))
    return scores


def drift_report(reference_path: Path, current_path: Path) -> dict[str, float | str]:
    reference = load_scores(reference_path)
    current = load_scores(current_path)
    psi = population_stability_index(reference, current)
    if psi >= 0.25:
        status = "high_drift"
    elif psi >= 0.10:
        status = "moderate_drift"
    else:
        status = "stable"
    return {
        "reference_count": float(len(reference)),
        "current_count": float(len(current)),
        "score_psi": psi,
        "status": status,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute a simple PSI drift report.")
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--current", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(drift_report(args.reference, args.current), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

