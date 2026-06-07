from __future__ import annotations

import argparse
from pathlib import Path

from videorank.features.offline import build_training_examples, read_events, write_jsonl


def run_local(events_path: Path, output_path: Path) -> None:
    events = read_events(events_path)
    examples = build_training_examples(events)
    write_jsonl((example.to_dict() for example in examples), output_path)


def run_beam(argv: list[str] | None = None) -> None:
    try:
        import apache_beam as beam
        from apache_beam.options.pipeline_options import PipelineOptions
    except ImportError as exc:
        raise SystemExit(
            "apache-beam is not installed. Install with `pip install -e .[pipelines]` "
            "or use `--runner local`."
        ) from exc

    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    known_args, pipeline_args = parser.parse_known_args(argv)

    # This Beam path intentionally keeps the transformation simple. The production
    # pattern is to keep feature logic in importable Python and reuse it in tests.
    with beam.Pipeline(options=PipelineOptions(pipeline_args)) as pipeline:
        (
            pipeline
            | "ReadEvents" >> beam.io.ReadFromText(known_args.input)
            | "WriteRawForDemo" >> beam.io.WriteToText(known_args.output, shard_name_template="")
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Feature pipeline local/Dataflow entrypoint.")
    parser.add_argument("--runner", choices=["local", "beam"], default="local")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args, passthrough = parser.parse_known_args()
    if args.runner == "local":
        run_local(args.input, args.output)
    else:
        run_beam(["--input", str(args.input), "--output", str(args.output), *passthrough])


if __name__ == "__main__":
    main()

