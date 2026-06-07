.PHONY: test generate train movielens compile-pipeline demo-api docker-build

test:
	PYTHONPATH=src python -m unittest discover -s tests

generate:
	PYTHONPATH=src python -m videorank.data.generate --output data/events.jsonl --users 200 --videos 80 --events 5000

train: generate
	PYTHONPATH=src python -m videorank.model.train --events data/events.jsonl --output-dir artifacts/model

movielens:
	PYTHONPATH=src python -m videorank.data.movielens --output data/movielens/events.jsonl --max-ratings 100000
	PYTHONPATH=src python -m videorank.model.train_movielens --events data/movielens/events.jsonl --output-dir artifacts/movielens-model

compile-pipeline:
	python pipelines/kfp/pipeline.py --output artifacts/pipelines/videorank_movielens_training.yaml

demo-api: train
	PYTHONPATH=src VIDEORANK_MODEL_PATH=artifacts/model/model.json python -m videorank.api.app

docker-build:
	docker build -t videorank-api:local .

