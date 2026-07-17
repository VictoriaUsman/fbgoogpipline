from common.versioning import write_versioned


def test_write_versioned_creates_file_with_no_prior_version(tmp_path):
    path = tmp_path / "silver" / "report.json"
    write_versioned(path, "first\n")

    assert path.read_text() == "first\n"
    assert not (path.parent / ".versions").exists()


def test_write_versioned_archives_prior_content_on_overwrite(tmp_path):
    path = tmp_path / "silver" / "report.json"
    write_versioned(path, "first\n")
    write_versioned(path, "second\n")

    assert path.read_text() == "second\n"
    versions_dir = path.parent / ".versions"
    assert (versions_dir / "report.json.v1").read_text() == "first\n"


def test_write_versioned_increments_version_number_on_each_overwrite(tmp_path):
    path = tmp_path / "silver" / "report.json"
    write_versioned(path, "v1\n")
    write_versioned(path, "v2\n")
    write_versioned(path, "v3\n")

    versions_dir = path.parent / ".versions"
    assert (versions_dir / "report.json.v1").read_text() == "v1\n"
    assert (versions_dir / "report.json.v2").read_text() == "v2\n"
    assert path.read_text() == "v3\n"


def test_versioned_backups_are_invisible_to_json_glob(tmp_path):
    # glue_jobs/bronze_to_silver.py and local_runner/run_pipeline.py both discover
    # records via `rglob("*.json")` -- a version file must never be mistaken for one.
    path = tmp_path / "silver" / "report.json"
    write_versioned(path, "first\n")
    write_versioned(path, "second\n")

    assert list(tmp_path.rglob("*.json")) == [path]
