import argparse
from pathlib import Path

MOVIELENS_LATEST_SMALL_URL = (
    "https://files.grouplens.org/datasets/movielens/ml-latest-small.zip"
)


def compile_pipeline(output: Path) -> None:
    try:
        from kfp import compiler, dsl
    except ImportError as exc:
        raise SystemExit(
            "kfp is not installed. Install with `pip install -e .[pipelines]`."
        ) from exc

    @dsl.component(base_image="python:3.11-slim")
    def prepare_movielens_events(
        dataset_url: str,
        max_ratings: int,
        data_snapshot_id: str,
        interactions: dsl.Output[dsl.Dataset],
    ) -> None:
        import csv
        import json
        import shutil
        import tempfile
        import urllib.request
        import zipfile
        from datetime import UTC, datetime
        from pathlib import Path

        def primary_genre(genres: str) -> str:
            first = genres.split("|")[0]
            if not first or first == "(no genres listed)":
                return "unknown"
            return first.lower().replace(" ", "_")

        output_dir = Path(interactions.path)
        output_dir.mkdir(parents=True, exist_ok=True)
        jsonl_path = output_dir / "events.jsonl"
        csv_path = output_dir / "interactions.csv"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            zip_path = tmp / "movielens.zip"
            with urllib.request.urlopen(dataset_url, timeout=60) as response, zip_path.open(
                "wb"
            ) as handle:
                shutil.copyfileobj(response, handle)
            with zipfile.ZipFile(zip_path) as archive:
                archive.extractall(tmp)
            dataset_dir = next(path for path in tmp.iterdir() if path.is_dir())

            with (dataset_dir / "movies.csv").open("r", encoding="utf-8", newline="") as handle:
                movies = {
                    row["movieId"]: {
                        "title": row["title"],
                        "category": primary_genre(row["genres"]),
                    }
                    for row in csv.DictReader(handle)
                }

            users = set()
            items = set()
            positives = 0
            rows = 0
            fieldnames = [
                "event_id",
                "user_id",
                "video_id",
                "category",
                "country",
                "device",
                "timestamp",
                "impression",
                "clicked",
                "watch_time_s",
                "completed",
                "rating",
                "label",
            ]
            with (
                (dataset_dir / "ratings.csv").open("r", encoding="utf-8", newline="")
                as ratings_handle,
                jsonl_path.open("w", encoding="utf-8") as jsonl_handle,
                csv_path.open("w", encoding="utf-8", newline="") as csv_handle,
            ):
                writer = csv.DictWriter(csv_handle, fieldnames=fieldnames)
                writer.writeheader()
                for index, row in enumerate(csv.DictReader(ratings_handle)):
                    if max_ratings > 0 and index >= max_ratings:
                        break
                    movie = movies.get(row["movieId"])
                    if movie is None:
                        continue
                    rating = float(row["rating"])
                    timestamp_epoch = int(row["timestamp"])
                    user_id = f"user_{row['userId']}"
                    video_id = f"movie_{row['movieId']}"
                    label = int(rating >= 4.0)
                    event = {
                        "event_id": f"movielens_{row['userId']}_{row['movieId']}_{timestamp_epoch}",
                        "user_id": user_id,
                        "video_id": video_id,
                        "video_title": movie["title"],
                        "category": movie["category"],
                        "country": "US",
                        "device": "web",
                        "timestamp": datetime.fromtimestamp(
                            timestamp_epoch, UTC
                        ).isoformat(),
                        "impression": 1,
                        "clicked": int(rating >= 3.0),
                        "watch_time_s": int(max(30, min(900, rating / 5.0 * 600))),
                        "completed": int(rating >= 4.5),
                        "rating": rating,
                        "label": label,
                    }
                    jsonl_handle.write(json.dumps(event, sort_keys=True) + "\n")
                    writer.writerow({key: event[key] for key in fieldnames})
                    users.add(user_id)
                    items.add(video_id)
                    positives += label
                    rows += 1

        interactions.metadata["dataset"] = "MovieLens latest-small"
        interactions.metadata["data_snapshot_id"] = data_snapshot_id
        interactions.metadata["rows"] = rows
        interactions.metadata["users"] = len(users)
        interactions.metadata["items"] = len(items)
        interactions.metadata["positives"] = positives
        interactions.metadata["csv_file"] = "interactions.csv"
        interactions.metadata["jsonl_file"] = "events.jsonl"

    @dsl.component(base_image="python:3.11-slim")
    def build_feature_table(
        interactions: dsl.Input[dsl.Dataset],
        data_snapshot_id: str,
        features: dsl.Output[dsl.Dataset],
    ) -> None:
        import csv
        import json
        from collections import defaultdict
        from pathlib import Path

        stats = defaultdict(
            lambda: {
                "interaction_count": 0,
                "positive_count": 0,
                "rating_sum": 0.0,
                "watch_time_sum": 0.0,
                "last_event_ts": "",
            }
        )
        events_path = Path(interactions.path) / "events.jsonl"
        for line in events_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            item = stats[row["user_id"]]
            item["interaction_count"] += 1
            item["positive_count"] += int(row["label"])
            item["rating_sum"] += float(row["rating"])
            item["watch_time_sum"] += float(row["watch_time_s"])
            item["last_event_ts"] = max(item["last_event_ts"], row["timestamp"])

        output_dir = Path(features.path)
        output_dir.mkdir(parents=True, exist_ok=True)
        jsonl_path = output_dir / "user_features.jsonl"
        csv_path = output_dir / "user_features.csv"
        fieldnames = [
            "user_id",
            "interaction_count",
            "positive_count",
            "positive_rate",
            "mean_rating",
            "mean_watch_time_s",
            "last_event_ts",
            "data_snapshot_id",
        ]
        rows = []
        for user_id, item in sorted(stats.items()):
            count = item["interaction_count"]
            rows.append(
                {
                    "user_id": user_id,
                    "interaction_count": count,
                    "positive_count": item["positive_count"],
                    "positive_rate": item["positive_count"] / count if count else 0.0,
                    "mean_rating": item["rating_sum"] / count if count else 0.0,
                    "mean_watch_time_s": item["watch_time_sum"] / count if count else 0.0,
                    "last_event_ts": item["last_event_ts"],
                    "data_snapshot_id": data_snapshot_id,
                }
            )
        with jsonl_path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        features.metadata["feature_set"] = "user_features"
        features.metadata["rows"] = len(rows)
        features.metadata["entity_id_column"] = "user_id"
        features.metadata["data_snapshot_id"] = data_snapshot_id

    @dsl.component(
        base_image="python:3.11-slim",
        packages_to_install=["google-cloud-aiplatform>=1.70"],
    )
    def register_vertex_dataset(
        interactions: dsl.Input[dsl.Dataset],
        project_id: str,
        location: str,
        data_snapshot_id: str,
        run_id: str,
        enable_vertex_datasets: bool,
        dataset_metadata: dsl.Output[dsl.Dataset],
    ) -> None:
        import json
        import re
        from pathlib import Path

        def clean(value: str) -> str:
            cleaned = re.sub(r"[^a-z0-9_-]", "-", value.lower()).strip("-")
            if cleaned and not cleaned[0].isalpha():
                cleaned = f"v-{cleaned}"
            return cleaned[:60].strip("-") or "run"

        output_dir = Path(dataset_metadata.path)
        output_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "enabled": enable_vertex_datasets,
            "resource_name": None,
            "display_name": None,
            "gcs_source": None,
            "reason": None,
        }
        if not enable_vertex_datasets:
            payload["reason"] = "disabled"
        elif not project_id:
            payload["reason"] = "missing_project_id"
        else:
            from google.cloud import aiplatform

            aiplatform.init(project=project_id, location=location)
            display_name = f"videorank-movielens-{clean(data_snapshot_id)}-{clean(run_id)}"
            gcs_source = f"{interactions.uri.rstrip('/')}/interactions.csv"
            dataset = aiplatform.TabularDataset.create(
                display_name=display_name,
                gcs_source=[gcs_source],
                sync=True,
            )
            payload.update(
                {
                    "resource_name": dataset.resource_name,
                    "display_name": display_name,
                    "gcs_source": gcs_source,
                }
            )
        (output_dir / "metadata.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )
        dataset_metadata.metadata.update({key: value for key, value in payload.items() if value})

    @dsl.component(
        base_image="python:3.11-slim",
        packages_to_install=[
            "google-cloud-aiplatform>=1.70",
            "google-cloud-bigquery>=3.25",
        ],
    )
    def publish_vertex_feature_store(
        features: dsl.Input[dsl.Dataset],
        project_id: str,
        location: str,
        bigquery_dataset: str,
        bigquery_location: str,
        feature_table_id: str,
        feature_online_store_id: str,
        feature_view_id: str,
        enable_vertex_feature_store: bool,
        feature_store_metadata: dsl.Output[dsl.Dataset],
    ) -> None:
        import json
        import time
        from pathlib import Path

        output_dir = Path(feature_store_metadata.path)
        output_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "bigquery_table": None,
            "bigquery_uri": None,
            "feature_online_store": None,
            "feature_view": None,
            "online_store_enabled": enable_vertex_feature_store,
            "reason": None,
        }
        if not project_id:
            payload["reason"] = "missing_project_id"
            (output_dir / "metadata.json").write_text(
                json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
            )
            return

        from google.cloud import bigquery

        client = bigquery.Client(project=project_id)
        dataset_ref = bigquery.Dataset(f"{project_id}.{bigquery_dataset}")
        dataset_ref.location = bigquery_location
        client.create_dataset(dataset_ref, exists_ok=True)

        table_id = f"{project_id}.{bigquery_dataset}.{feature_table_id}"
        schema = [
            bigquery.SchemaField("user_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("interaction_count", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("positive_count", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("positive_rate", "FLOAT", mode="REQUIRED"),
            bigquery.SchemaField("mean_rating", "FLOAT", mode="REQUIRED"),
            bigquery.SchemaField("mean_watch_time_s", "FLOAT", mode="REQUIRED"),
            bigquery.SchemaField("last_event_ts", "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("data_snapshot_id", "STRING", mode="REQUIRED"),
        ]
        job_config = bigquery.LoadJobConfig(
            schema=schema,
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        )
        with (Path(features.path) / "user_features.jsonl").open("rb") as handle:
            load_job = client.load_table_from_file(handle, table_id, job_config=job_config)
        load_job.result()
        bq_uri = f"bq://{project_id}.{bigquery_dataset}.{feature_table_id}"
        payload["bigquery_table"] = table_id
        payload["bigquery_uri"] = bq_uri

        if enable_vertex_feature_store:
            from google.cloud import aiplatform
            from vertexai.resources.preview import feature_store

            aiplatform.init(project=project_id, location=location)
            try:
                online_store = feature_store.FeatureOnlineStore(feature_online_store_id)
                online_store_name = online_store.resource_name
            except Exception:
                online_store = feature_store.FeatureOnlineStore.create_optimized_store(
                    feature_online_store_id
                )
                online_store_name = online_store.resource_name

            try:
                feature_view = online_store.create_feature_view(
                    name=feature_view_id,
                    source=feature_store.utils.FeatureViewBigQuerySource(
                        uri=bq_uri,
                        entity_id_columns=["user_id"],
                    ),
                )
                feature_view_name = feature_view.resource_name
            except Exception as exc:
                message = str(exc)
                if "already exists" not in message.lower():
                    raise
                feature_view_name = (
                    f"projects/{project_id}/locations/{location}/featureOnlineStores/"
                    f"{feature_online_store_id}/featureViews/{feature_view_id}"
                )
            payload["feature_online_store"] = online_store_name
            payload["feature_view"] = feature_view_name
            payload["created_or_updated_at"] = int(time.time())
        else:
            payload["reason"] = "online_feature_store_disabled_cost_guardrail"

        (output_dir / "metadata.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )
        feature_store_metadata.metadata.update(
            {key: value for key, value in payload.items() if value}
        )

    @dsl.component(
        base_image="python:3.11-slim",
        packages_to_install=["numpy>=2.0,<3"],
    )
    def train_matrix_factorization(
        interactions: dsl.Input[dsl.Dataset],
        factors: int,
        epochs: int,
        learning_rate: float,
        regularization: float,
        seed: int,
        model: dsl.Output[dsl.Model],
        evaluation_rows: dsl.Output[dsl.Dataset],
    ) -> None:
        import json
        import math
        from collections import defaultdict
        from pathlib import Path

        import numpy as np

        def sigmoid(value: float) -> float:
            if value < -50:
                return 0.0
            if value > 50:
                return 1.0
            return 1.0 / (1.0 + math.exp(-value))

        def score(user_index: int, item_index: int) -> float:
            return float(
                global_bias
                + user_bias[user_index]
                + item_bias[item_index]
                + (user_factors[user_index] * item_factors[item_index]).sum()
            )

        interactions_path = Path(interactions.path) / "events.jsonl"
        rows = [
            json.loads(line)
            for line in interactions_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        rows = sorted(rows, key=lambda row: row["timestamp"])
        split_at = max(1, int(len(rows) * 0.8))
        train_rows = rows[:split_at]
        eval_rows = rows[split_at:]

        user_to_index = {
            user_id: index
            for index, user_id in enumerate(sorted({row["user_id"] for row in train_rows}))
        }
        item_to_index = {
            item_id: index
            for index, item_id in enumerate(sorted({row["video_id"] for row in train_rows}))
        }
        rng = np.random.default_rng(seed)
        user_factors = rng.normal(0, 0.05, size=(len(user_to_index), factors))
        item_factors = rng.normal(0, 0.05, size=(len(item_to_index), factors))
        user_bias = np.zeros(len(user_to_index))
        item_bias = np.zeros(len(item_to_index))
        labels = np.array([int(row["label"]) for row in train_rows], dtype=np.float64)
        positive_rate = min(0.99, max(0.01, float(labels.mean())))
        global_bias = math.log(positive_rate / (1 - positive_rate))

        train_indices = np.array(
            [
                (user_to_index[row["user_id"]], item_to_index[row["video_id"]])
                for row in train_rows
            ],
            dtype=np.int64,
        )
        for _ in range(epochs):
            for row_index in rng.permutation(len(train_rows)):
                user_index, item_index = train_indices[row_index]
                label = labels[row_index]
                user_vector = user_factors[user_index].copy()
                item_vector = item_factors[item_index].copy()
                error = sigmoid(score(user_index, item_index)) - label
                user_bias[user_index] -= learning_rate * (
                    error + regularization * user_bias[user_index]
                )
                item_bias[item_index] -= learning_rate * (
                    error + regularization * item_bias[item_index]
                )
                user_factors[user_index] -= learning_rate * (
                    error * item_vector + regularization * user_vector
                )
                item_factors[item_index] -= learning_rate * (
                    error * user_vector + regularization * item_vector
                )

        item_counts = defaultdict(lambda: [0, 0])
        item_metadata = {}
        rating_sums = defaultdict(float)
        global_positive = 0
        for row in train_rows:
            item_counts[row["video_id"]][0] += 1
            item_counts[row["video_id"]][1] += int(row["label"])
            rating_sums[row["video_id"]] += float(row.get("rating", 0.0))
            item_metadata.setdefault(
                row["video_id"],
                {
                    "video_id": row["video_id"],
                    "video_title": row.get("video_title", row["video_id"]),
                    "category": row.get("category", "unknown"),
                },
            )
            global_positive += int(row["label"])
        global_rate = (global_positive + 2.0) / (len(train_rows) + 4.0)
        catalog = []
        for video_id, counts in item_counts.items():
            ratings = counts[0]
            positives = counts[1]
            item = dict(item_metadata[video_id])
            item.update(
                {
                    "ratings": ratings,
                    "impressions": ratings,
                    "positive_labels": positives,
                    "positive_rate": (positives + 2.0) / (ratings + 4.0),
                    "mean_rating": rating_sums[video_id] / ratings if ratings else 0.0,
                }
            )
            catalog.append(item)
        catalog = sorted(
            catalog,
            key=lambda item: (item["positive_rate"], item["ratings"]),
            reverse=True,
        )[:500]

        eval_dir = Path(evaluation_rows.path)
        eval_dir.mkdir(parents=True, exist_ok=True)
        eval_output = eval_dir / "evaluation_rows.jsonl"
        with eval_output.open("w", encoding="utf-8") as handle:
            for row in eval_rows:
                user_index = user_to_index.get(row["user_id"])
                item_index = item_to_index.get(row["video_id"])
                model_score = (
                    sigmoid(global_bias)
                    if user_index is None or item_index is None
                    else sigmoid(score(user_index, item_index))
                )
                counts = item_counts[row["video_id"]]
                baseline_score = (counts[1] + global_rate * 8.0) / (counts[0] + 8.0)
                handle.write(
                    json.dumps(
                        {
                            "user_id": row["user_id"],
                            "video_id": row["video_id"],
                            "label": int(row["label"]),
                            "model_score": model_score,
                            "baseline_score": baseline_score,
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )

        model_payload = {
            "model_type": "matrix_factorization",
            "dataset": "MovieLens latest-small",
            "factors": factors,
            "epochs": epochs,
            "user_to_index": user_to_index,
            "item_to_index": item_to_index,
            "user_factors": user_factors.tolist(),
            "item_factors": item_factors.tolist(),
            "user_bias": user_bias.tolist(),
            "item_bias": item_bias.tolist(),
            "global_bias": global_bias,
            "train_interactions": len(train_rows),
            "eval_interactions": len(eval_rows),
            "catalog": catalog,
        }
        model_dir = Path(model.path)
        model_dir.mkdir(parents=True, exist_ok=True)
        model_path = model_dir / "model.json"
        model_path.write_text(json.dumps(model_payload, sort_keys=True), encoding="utf-8")
        model.metadata["model_type"] = "matrix_factorization"
        model.metadata["dataset"] = "MovieLens latest-small"
        model.metadata["framework"] = "numpy"
        evaluation_rows.metadata["rows"] = len(eval_rows)

    @dsl.component(base_image="python:3.11-slim")
    def evaluate_ranker(
        evaluation_rows: dsl.Input[dsl.Dataset],
        metrics: dsl.Output[dsl.Metrics],
        metrics_json: dsl.Output[dsl.Dataset],
    ) -> None:
        import json
        import math
        from collections import defaultdict
        from pathlib import Path

        evaluation_path = Path(evaluation_rows.path) / "evaluation_rows.jsonl"
        rows = [
            json.loads(line)
            for line in evaluation_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

        def auc(labels: list[int], scores: list[float]) -> float:
            positives = [score for label, score in zip(labels, scores, strict=True) if label == 1]
            negatives = [score for label, score in zip(labels, scores, strict=True) if label == 0]
            if not positives or not negatives:
                return 0.5
            wins = 0.0
            for positive in positives:
                for negative in negatives:
                    if positive > negative:
                        wins += 1.0
                    elif positive == negative:
                        wins += 0.5
            return wins / (len(positives) * len(negatives))

        def brier(labels: list[int], scores: list[float]) -> float:
            return sum(
                (score - label) ** 2 for label, score in zip(labels, scores, strict=True)
            ) / len(labels)

        def grouped_scores(score_key: str) -> dict[str, list[tuple[int, float]]]:
            groups = defaultdict(list)
            for row in rows:
                groups[row["user_id"]].append((int(row["label"]), float(row[score_key])))
            return groups

        def recall_at_k(groups: dict[str, list[tuple[int, float]]], k: int) -> float:
            recalls = []
            for group_rows in groups.values():
                positives = sum(label for label, _ in group_rows)
                if positives == 0:
                    continue
                top_k = sorted(group_rows, key=lambda item: item[1], reverse=True)[:k]
                recalls.append(sum(label for label, _ in top_k) / positives)
            return sum(recalls) / len(recalls) if recalls else 0.0

        def ndcg_at_k(groups: dict[str, list[tuple[int, float]]], k: int) -> float:
            values = []
            for group_rows in groups.values():
                ranked = sorted(group_rows, key=lambda item: item[1], reverse=True)[:k]
                ideal = sorted(group_rows, key=lambda item: item[0], reverse=True)[:k]
                dcg = sum(
                    (2**label - 1) / math.log2(index + 2)
                    for index, (label, _) in enumerate(ranked)
                )
                idcg = sum(
                    (2**label - 1) / math.log2(index + 2)
                    for index, (label, _) in enumerate(ideal)
                )
                if idcg > 0:
                    values.append(dcg / idcg)
            return sum(values) / len(values) if values else 0.0

        labels = [int(row["label"]) for row in rows]
        model_scores = [float(row["model_score"]) for row in rows]
        baseline_scores = [float(row["baseline_score"]) for row in rows]
        model_groups = grouped_scores("model_score")
        baseline_groups = grouped_scores("baseline_score")
        payload = {
            "model_auc": auc(labels, model_scores),
            "baseline_auc": auc(labels, baseline_scores),
            "model_brier": brier(labels, model_scores),
            "baseline_brier": brier(labels, baseline_scores),
            "model_recall_at_10": recall_at_k(model_groups, 10),
            "baseline_recall_at_10": recall_at_k(baseline_groups, 10),
            "model_ndcg_at_10": ndcg_at_k(model_groups, 10),
            "baseline_ndcg_at_10": ndcg_at_k(baseline_groups, 10),
            "eval_interactions": float(len(rows)),
        }
        payload["ndcg_at_10_lift"] = (
            payload["model_ndcg_at_10"] - payload["baseline_ndcg_at_10"]
        )
        payload["recall_at_10_lift"] = (
            payload["model_recall_at_10"] - payload["baseline_recall_at_10"]
        )
        for name, value in payload.items():
            metrics.log_metric(name, float(value))
        output_dir = Path(metrics_json.path)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "metrics.json"
        output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        metrics_json.metadata["rows"] = len(rows)

    @dsl.component(
        base_image="python:3.11-slim",
        packages_to_install=["google-cloud-aiplatform>=1.70"],
    )
    def log_vertex_experiment(
        metrics_json: dsl.Input[dsl.Dataset],
        project_id: str,
        location: str,
        experiment_name: str,
        run_id: str,
        git_sha: str,
        data_snapshot_id: str,
        factors: int,
        epochs: int,
        learning_rate: float,
        regularization: float,
        enable_vertex_experiments: bool,
        experiment_metadata: dsl.Output[dsl.Dataset],
    ) -> None:
        import json
        import re
        from pathlib import Path

        def clean(value: str) -> str:
            cleaned = re.sub(r"[^a-z0-9_-]", "-", value.lower()).strip("-")
            if cleaned and not cleaned[0].isalpha():
                cleaned = f"v-{cleaned}"
            return cleaned[:60].strip("-") or "run"

        output_dir = Path(experiment_metadata.path)
        output_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "enabled": enable_vertex_experiments,
            "experiment_name": experiment_name,
            "run_name": clean(f"{run_id}-{git_sha[:7]}"),
            "reason": None,
        }
        if not enable_vertex_experiments:
            payload["reason"] = "disabled"
        elif not project_id:
            payload["reason"] = "missing_project_id"
        else:
            from google.cloud import aiplatform

            metrics = json.loads(
                (Path(metrics_json.path) / "metrics.json").read_text(encoding="utf-8")
            )
            params = {
                "data_snapshot_id": data_snapshot_id,
                "git_sha": git_sha,
                "factors": factors,
                "epochs": epochs,
                "learning_rate": learning_rate,
                "regularization": regularization,
            }
            aiplatform.init(project=project_id, location=location, experiment=experiment_name)
            aiplatform.start_run(run=payload["run_name"])
            try:
                aiplatform.log_params(params)
                aiplatform.log_metrics({key: float(value) for key, value in metrics.items()})
            finally:
                aiplatform.end_run()
            payload["resource_hint"] = (
                f"projects/{project_id}/locations/{location}/metadataStores/default/"
                f"contexts/{experiment_name}-{payload['run_name']}"
            )
        (output_dir / "metadata.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )
        experiment_metadata.metadata.update(
            {key: value for key, value in payload.items() if value}
        )

    @dsl.component(base_image="python:3.11-slim")
    def quality_gate(
        metrics_json: dsl.Input[dsl.Dataset],
        min_model_ndcg_at_10: float,
        min_ndcg_lift: float,
    ) -> str:
        import json
        from pathlib import Path

        metrics = json.loads((Path(metrics_json.path) / "metrics.json").read_text(encoding="utf-8"))
        if metrics["model_ndcg_at_10"] < min_model_ndcg_at_10:
            raise RuntimeError(
                "quality gate failed: "
                f"model_ndcg_at_10={metrics['model_ndcg_at_10']:.4f} "
                f"< {min_model_ndcg_at_10:.4f}"
            )
        if metrics["ndcg_at_10_lift"] < min_ndcg_lift:
            raise RuntimeError(
                "quality gate failed: "
                f"ndcg_at_10_lift={metrics['ndcg_at_10_lift']:.4f} "
                f"< {min_ndcg_lift:.4f}"
            )
        return "passed"

    @dsl.component(
        base_image="python:3.11-slim",
        packages_to_install=["google-cloud-aiplatform>=1.70"],
    )
    def register_vertex_model(
        model: dsl.Input[dsl.Model],
        metrics_json: dsl.Input[dsl.Dataset],
        gate_result: str,
        project_id: str,
        location: str,
        git_sha: str,
        run_id: str,
        serving_container_image_uri: str,
        enable_vertex_model_registry: bool,
        vertex_model_metadata: dsl.Output[dsl.Dataset],
    ) -> None:
        import json
        import re
        from pathlib import Path

        def clean(value: str) -> str:
            cleaned = re.sub(r"[^a-z0-9_-]", "-", value.lower()).strip("-")
            if cleaned and not cleaned[0].isalpha():
                cleaned = f"v-{cleaned}"
            return cleaned[:60].strip("-") or "run"

        output_dir = Path(vertex_model_metadata.path)
        output_dir.mkdir(parents=True, exist_ok=True)
        metrics = json.loads((Path(metrics_json.path) / "metrics.json").read_text(encoding="utf-8"))
        payload = {
            "enabled": enable_vertex_model_registry,
            "resource_name": None,
            "display_name": None,
            "artifact_uri": model.uri,
            "serving_container_image_uri": serving_container_image_uri,
            "gate_result": gate_result,
            "metrics": metrics,
            "reason": None,
        }
        if not enable_vertex_model_registry:
            payload["reason"] = "disabled"
        elif not project_id:
            payload["reason"] = "missing_project_id"
        else:
            from google.cloud import aiplatform

            image_uri = serving_container_image_uri or (
                f"{location}-docker.pkg.dev/{project_id}/videorank/videorank-api:{git_sha}"
            )
            display_name = f"videorank-ranker-{clean(run_id)}-{clean(git_sha[:7])}"
            aiplatform.init(project=project_id, location=location)
            uploaded = aiplatform.Model.upload(
                display_name=display_name,
                artifact_uri=model.uri,
                serving_container_image_uri=image_uri,
                serving_container_predict_route="/recommendations",
                serving_container_health_route="/health",
                serving_container_ports=[8080],
                description=(
                    "VideoRank MovieLens candidate registered by CT. Serving remains "
                    "Cloud Run/GitOps unless explicitly promoted."
                ),
                labels={
                    "app": "videorank",
                    "workflow": "continuous_training",
                    "git_sha": clean(git_sha),
                    "run_id": clean(run_id),
                },
                sync=True,
            )
            payload.update(
                {
                    "resource_name": uploaded.resource_name,
                    "display_name": display_name,
                    "serving_container_image_uri": image_uri,
                }
            )
        (output_dir / "metadata.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )
        vertex_model_metadata.metadata.update(
            {key: value for key, value in payload.items() if value}
        )

    @dsl.component(base_image="python:3.11-slim")
    def register_model_metadata(
        model: dsl.Input[dsl.Model],
        metrics_json: dsl.Input[dsl.Dataset],
        dataset_metadata: dsl.Input[dsl.Dataset],
        feature_store_metadata: dsl.Input[dsl.Dataset],
        experiment_metadata: dsl.Input[dsl.Dataset],
        vertex_model_metadata: dsl.Input[dsl.Dataset],
        gate_result: str,
        data_snapshot_id: str,
        git_sha: str,
        run_id: str,
        registration: dsl.Output[dsl.Dataset],
    ) -> None:
        import json
        from datetime import UTC, datetime
        from pathlib import Path

        def read_metadata(artifact) -> dict:
            path = Path(artifact.path) / "metadata.json"
            if not path.exists():
                return {"missing": str(path)}
            return json.loads(path.read_text(encoding="utf-8"))

        metrics = json.loads((Path(metrics_json.path) / "metrics.json").read_text(encoding="utf-8"))
        payload = {
            "registered_at": datetime.now(UTC).isoformat(),
            "gate_result": gate_result,
            "model_uri": model.uri,
            "data_snapshot_id": data_snapshot_id,
            "git_sha": git_sha,
            "run_id": run_id,
            "metrics": metrics,
            "vertex_dataset": read_metadata(dataset_metadata),
            "vertex_feature_store": read_metadata(feature_store_metadata),
            "vertex_experiment": read_metadata(experiment_metadata),
            "vertex_model_registry": read_metadata(vertex_model_metadata),
            "promotion_policy": "open GitOps PR only after offline gate and review",
        }
        output_dir = Path(registration.path)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "registration.json"
        output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        registration.metadata["gate_result"] = gate_result
        registration.metadata["model_uri"] = model.uri
        registration.metadata["data_snapshot_id"] = data_snapshot_id
        registration.metadata["git_sha"] = git_sha
        registration.metadata["run_id"] = run_id

    @dsl.pipeline(
        name="videorank-movielens-training",
        description="Train a VideoRank recommender on the real MovieLens interaction dataset.",
    )
    def videorank_movielens_training(
        dataset_url: str = MOVIELENS_LATEST_SMALL_URL,
        max_ratings: int = 25000,
        data_snapshot_id: str = "movielens-latest-small-static",
        git_sha: str = "local",
        run_id: str = "local",
        project_id: str = "",
        location: str = "europe-west1",
        bigquery_dataset: str = "videorank",
        bigquery_location: str = "EU",
        feature_table_id: str = "vertex_user_features",
        feature_online_store_id: str = "videorank_dev_store",
        feature_view_id: str = "user_features",
        experiment_name: str = "videorank-continuous-training",
        serving_container_image_uri: str = "",
        enable_vertex_datasets: bool = True,
        enable_vertex_feature_store: bool = False,
        enable_vertex_experiments: bool = True,
        enable_vertex_model_registry: bool = True,
        factors: int = 24,
        epochs: int = 8,
        learning_rate: float = 0.05,
        regularization: float = 0.002,
        seed: int = 7,
        min_model_ndcg_at_10: float = 0.05,
        min_ndcg_lift: float = -0.02,
    ) -> None:
        prepared = prepare_movielens_events(
            dataset_url=dataset_url,
            max_ratings=max_ratings,
            data_snapshot_id=data_snapshot_id,
        )
        feature_rows = build_feature_table(
            interactions=prepared.outputs["interactions"],
            data_snapshot_id=data_snapshot_id,
        )
        vertex_dataset = register_vertex_dataset(
            interactions=prepared.outputs["interactions"],
            project_id=project_id,
            location=location,
            data_snapshot_id=data_snapshot_id,
            run_id=run_id,
            enable_vertex_datasets=enable_vertex_datasets,
        )
        vertex_features = publish_vertex_feature_store(
            features=feature_rows.outputs["features"],
            project_id=project_id,
            location=location,
            bigquery_dataset=bigquery_dataset,
            bigquery_location=bigquery_location,
            feature_table_id=feature_table_id,
            feature_online_store_id=feature_online_store_id,
            feature_view_id=feature_view_id,
            enable_vertex_feature_store=enable_vertex_feature_store,
        )
        trained = train_matrix_factorization(
            interactions=prepared.outputs["interactions"],
            factors=factors,
            epochs=epochs,
            learning_rate=learning_rate,
            regularization=regularization,
            seed=seed,
        )
        evaluated = evaluate_ranker(evaluation_rows=trained.outputs["evaluation_rows"])
        experiment = log_vertex_experiment(
            metrics_json=evaluated.outputs["metrics_json"],
            project_id=project_id,
            location=location,
            experiment_name=experiment_name,
            run_id=run_id,
            git_sha=git_sha,
            data_snapshot_id=data_snapshot_id,
            factors=factors,
            epochs=epochs,
            learning_rate=learning_rate,
            regularization=regularization,
            enable_vertex_experiments=enable_vertex_experiments,
        )
        gate = quality_gate(
            metrics_json=evaluated.outputs["metrics_json"],
            min_model_ndcg_at_10=min_model_ndcg_at_10,
            min_ndcg_lift=min_ndcg_lift,
        )
        vertex_model = register_vertex_model(
            model=trained.outputs["model"],
            metrics_json=evaluated.outputs["metrics_json"],
            gate_result=gate.output,
            project_id=project_id,
            location=location,
            git_sha=git_sha,
            run_id=run_id,
            serving_container_image_uri=serving_container_image_uri,
            enable_vertex_model_registry=enable_vertex_model_registry,
        )
        register_model_metadata(
            model=trained.outputs["model"],
            metrics_json=evaluated.outputs["metrics_json"],
            dataset_metadata=vertex_dataset.outputs["dataset_metadata"],
            feature_store_metadata=vertex_features.outputs["feature_store_metadata"],
            experiment_metadata=experiment.outputs["experiment_metadata"],
            vertex_model_metadata=vertex_model.outputs["vertex_model_metadata"],
            gate_result=gate.output,
            data_snapshot_id=data_snapshot_id,
            git_sha=git_sha,
            run_id=run_id,
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    compiler.Compiler().compile(
        pipeline_func=videorank_movielens_training,
        package_path=str(output),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile the KFP v2 MovieLens pipeline.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/pipelines/videorank_movielens_training.yaml"),
    )
    args = parser.parse_args()
    compile_pipeline(args.output)
    print(f"compiled pipeline to {args.output}")


if __name__ == "__main__":
    main()
