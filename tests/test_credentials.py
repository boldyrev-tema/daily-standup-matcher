import pytest
from credentials import load_credential


def test_load_credential_reads_value(tmp_path):
    env_file = tmp_path / "fake.env"
    env_file.write_text("SOME_KEY=abc123\nOTHER_KEY=xyz\n")
    assert load_credential(str(env_file), "SOME_KEY") == "abc123"


def test_load_credential_raises_when_missing(tmp_path):
    env_file = tmp_path / "fake.env"
    env_file.write_text("OTHER_KEY=xyz\n")
    with pytest.raises(ValueError):
        load_credential(str(env_file), "SOME_KEY")
