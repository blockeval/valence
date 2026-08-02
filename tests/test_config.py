from pathlib import Path

import pytest
import yaml

from valence.config import load_config


def test_invalid_committee_fraction_is_rejected(tmp_path: Path):
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump({"protocol": {"committee_fraction": 1.5}}))
    with pytest.raises(ValueError, match="committee_fraction"):
        load_config(path)


def test_explicit_stake_length_must_match_validator_count(tmp_path: Path):
    path = tmp_path / "bad-stakes.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "validators": {
                    "count": 4,
                    "stake_distribution": "explicit",
                    "explicit_stakes": [0.5, 0.5],
                },
                "topology": {"degree": 2},
            }
        )
    )
    with pytest.raises(ValueError, match="explicit_stakes length"):
        load_config(path)
