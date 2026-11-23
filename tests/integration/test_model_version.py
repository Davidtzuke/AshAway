"""I11: the deployed model is the version the latest training run produced.

Compares models/live-v1 with reports/training_record.json, which the training run
writes together. If someone retrains without redeploying, or the other way round,
this fails.
"""
import json

import pytest

from ashaway.model.data import LIVE_FEATURES

from conftest import BUNDLE_DIR

RECORD = BUNDLE_DIR.parent.parent / "reports" / "training_record.json"


@pytest.fixture(scope="module")
def record():
    return json.loads(RECORD.read_text(encoding="utf-8"))


def test_I11_deployed_version_and_cut_offs_match_the_training_record(bundle, record):
    live = record["live_bundle"]
    assert (bundle.version, bundle.medium_from, bundle.high_from) == (live["version"], live["medium_from"], live["high_from"])


def test_I11_deployed_features_match_the_training_record(bundle, record):
    assert bundle.features == record["models"]["xgboost_live"]["features"] == LIVE_FEATURES


def test_I11_deployed_model_uses_the_rounds_early_stopping_chose(bundle, record):
    # The file keeps every tree that was built; predictions use only the best rounds.
    assert bundle.model.best_iteration + 1 == record["models"]["xgboost_live"]["boosting_rounds"]


def test_I11_training_record_is_from_real_data(record):
    assert record["data"] == "mesogeos_track_a"
    assert record["data_report"]["clean_samples"] == 25722
