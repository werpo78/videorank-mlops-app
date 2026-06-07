from __future__ import annotations

import argparse
from pathlib import Path


def compile_pipeline(output: Path) -> None:
    try:
        from kfp import compiler, dsl
    except ImportError as exc:
        raise SystemExit("kfp is not installed. Install with `pip install -e .[pipelines]`.") from exc

    @dsl.component(base_image="python:3.11-slim")
    def ingest_events(seed: int, output_path: dsl.OutputPath(str)) -> None:
        import json
        import random

        rng = random.Random(seed)
        with open(output_path, "w", encoding="utf-8") as handle:
            for index in range(100):
                handle.write(json.dumps({"event_id": index, "clicked": int(rng.random() > 0.8)}) + "\n")

    @dsl.component(base_image="python:3.11-slim")
    def train_model(events_path: dsl.InputPath(str), metrics_path: dsl.OutputPath(str)) -> None:
        import json

        with open(events_path, encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle]
        click_rate = sum(row["clicked"] for row in rows) / len(rows)
        with open(metrics_path, "w", encoding="utf-8") as handle:
            json.dump({"click_rate": click_rate, "rows": len(rows)}, handle)

    @dsl.component(base_image="python:3.11-slim")
    def register_model(metrics_path: dsl.InputPath(str), min_click_rate: float) -> str:
        import json

        with open(metrics_path, encoding="utf-8") as handle:
            metrics = json.load(handle)
        if metrics["click_rate"] < min_click_rate:
            raise RuntimeError("model quality gate failed")
        return "registered"

    @dsl.pipeline(name="videorank-training")
    def videorank_training(seed: int = 7, min_click_rate: float = 0.05) -> None:
        ingest = ingest_events(seed=seed)
        train = train_model(events_path=ingest.outputs["output_path"])
        register_model(metrics_path=train.outputs["metrics_path"], min_click_rate=min_click_rate)

    output.parent.mkdir(parents=True, exist_ok=True)
    compiler.Compiler().compile(pipeline_func=videorank_training, package_path=str(output))


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile the KFP v2 pipeline.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/pipelines/videorank_training.yaml"))
    args = parser.parse_args()
    compile_pipeline(args.output)
    print(f"compiled pipeline to {args.output}")


if __name__ == "__main__":
    main()

