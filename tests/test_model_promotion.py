from __future__ import annotations

import argparse
import importlib.util
import tempfile
import unittest
from pathlib import Path

import yaml

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "promote_model_to_config.py"


class ModelPromotionTests(unittest.TestCase):
    def test_promote_model_updates_values_env(self) -> None:
        spec = importlib.util.spec_from_file_location("promote_model_to_config", SCRIPT_PATH)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as tmpdir:
            values_path = Path(tmpdir) / "values.yaml"
            values_path.write_text(
                '''image:
  repository: repo # {"$imagepolicy": "flux-system:videorank-api:name"}
  tag: main-1-abc1234 # {"$imagepolicy": "flux-system:videorank-api:tag"}
  digest: sha256:old # {"$imagepolicy": "flux-system:videorank-api:digest"}
env:
  VIDEORANK_ENV: dev
''',
                encoding="utf-8",
            )
            args = argparse.Namespace(
                values_path=values_path,
                model_artifact_uri="gs://bucket/path/model",
                model_version="model-123",
                vertex_model_resource="projects/p/locations/europe-west1/models/1@2",
                git_sha="abc123",
                data_snapshot_id="snapshot-1",
                promotion_reason="approved",
                promoted_at="2026-06-07T00:00:00+00:00",
            )
            module.update_values(values_path, args)
            text = values_path.read_text(encoding="utf-8")
            values = yaml.safe_load(text)

        self.assertIn('{"$imagepolicy": "flux-system:videorank-api:digest"}', text)

        env = values["env"]
        self.assertEqual(env["VIDEORANK_MODEL_URI"], "gs://bucket/path/model")
        self.assertEqual(env["VIDEORANK_MODEL_VERSION"], "model-123")
        self.assertEqual(
            env["VIDEORANK_VERTEX_MODEL_RESOURCE"],
            "projects/p/locations/europe-west1/models/1@2",
        )
        self.assertEqual(env["VIDEORANK_DATA_SNAPSHOT_ID"], "snapshot-1")
        self.assertEqual(env["VIDEORANK_MODEL_PROMOTION_REASON"], "approved")


if __name__ == "__main__":
    unittest.main()
