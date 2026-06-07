from __future__ import annotations

import math
from collections import defaultdict
from typing import Iterable


def auc_score(labels: list[int], scores: list[float]) -> float:
    positives = [(score, label) for score, label in zip(scores, labels, strict=True) if label == 1]
    negatives = [(score, label) for score, label in zip(scores, labels, strict=True) if label == 0]
    if not positives or not negatives:
        return 0.5
    wins = 0.0
    for positive_score, _ in positives:
        for negative_score, _ in negatives:
            if positive_score > negative_score:
                wins += 1.0
            elif positive_score == negative_score:
                wins += 0.5
    return wins / (len(positives) * len(negatives))


def recall_at_k(grouped_labels_scores: dict[str, list[tuple[int, float]]], k: int = 10) -> float:
    recalls: list[float] = []
    for rows in grouped_labels_scores.values():
        positives = sum(label for label, _ in rows)
        if positives == 0:
            continue
        top_k = sorted(rows, key=lambda item: item[1], reverse=True)[:k]
        recalls.append(sum(label for label, _ in top_k) / positives)
    return sum(recalls) / len(recalls) if recalls else 0.0


def ndcg_at_k(grouped_labels_scores: dict[str, list[tuple[int, float]]], k: int = 10) -> float:
    values: list[float] = []
    for rows in grouped_labels_scores.values():
        ranked = sorted(rows, key=lambda item: item[1], reverse=True)[:k]
        ideal = sorted(rows, key=lambda item: item[0], reverse=True)[:k]
        dcg = sum((2**label - 1) / math.log2(index + 2) for index, (label, _) in enumerate(ranked))
        idcg = sum((2**label - 1) / math.log2(index + 2) for index, (label, _) in enumerate(ideal))
        if idcg > 0:
            values.append(dcg / idcg)
    return sum(values) / len(values) if values else 0.0


def grouped_by_user(
    user_ids: Iterable[str], labels: Iterable[int], scores: Iterable[float]
) -> dict[str, list[tuple[int, float]]]:
    groups: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for user_id, label, score in zip(user_ids, labels, scores, strict=True):
        groups[user_id].append((label, score))
    return groups


def brier_score(labels: list[int], scores: list[float]) -> float:
    if not labels:
        return 0.0
    return sum((score - label) ** 2 for label, score in zip(labels, scores, strict=True)) / len(labels)


def population_stability_index(
    expected: list[float], actual: list[float], buckets: int = 10, epsilon: float = 1e-6
) -> float:
    if not expected or not actual:
        return 0.0
    min_value = min(expected + actual)
    max_value = max(expected + actual)
    if min_value == max_value:
        return 0.0
    width = (max_value - min_value) / buckets

    def bucket_counts(values: list[float]) -> list[float]:
        counts = [0 for _ in range(buckets)]
        for value in values:
            index = min(buckets - 1, int((value - min_value) / width))
            counts[index] += 1
        total = len(values)
        return [max(epsilon, count / total) for count in counts]

    expected_rates = bucket_counts(expected)
    actual_rates = bucket_counts(actual)
    return sum((actual_rate - expected_rate) * math.log(actual_rate / expected_rate) for expected_rate, actual_rate in zip(expected_rates, actual_rates, strict=True))

