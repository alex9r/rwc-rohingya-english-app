"""Recording deletion and reviewer-correction storage, with the database faked."""

import pytest

from app import db, recordings, reviews


class FakeConn:
    """Records statements; ``rows`` feeds the next SELECT, ``one`` the next fetchone."""

    def __init__(self, rows=(), one=None):
        self.statements = []
        self._rows = list(rows)
        self._one = one
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.rolled_back = exc_type is not None
        return False

    def execute(self, statement, params=()):
        self.statements.append((statement, params))
        return self

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._one


class FakeStore:
    def __init__(self, fail_on=None):
        self.deleted = []
        self.fail_on = fail_on

    def delete(self, key):
        if key == self.fail_on:
            raise RuntimeError("boom")
        self.deleted.append(key)


@pytest.fixture
def patch_db(monkeypatch):
    def install(conn):
        monkeypatch.setattr(db, "_connect", lambda: conn)
        monkeypatch.setattr(db, "ensure_vocabulary_schema", lambda c: None)
        return conn

    return install


def test_delete_removes_objects_rows_and_logs_without_content(patch_db):
    conn = patch_db(FakeConn(rows=[(1, "rec/S007/a.m4a", "app"), (2, "rec/S007/b.m4a", "app")]))
    store = FakeStore()
    assert recordings.delete_speaker_recordings("S007", store, "email") == 2
    assert store.deleted == ["rec/S007/a.m4a", "rec/S007/b.m4a"]
    deletes = [s for s in conn.statements if s[0].startswith("DELETE FROM recordings")]
    assert [p for _, p in deletes] == [(1,), (2,)]
    log = [s for s in conn.statements if "INSERT INTO recording_deletions" in s[0]][0]
    assert log[1] == ("S007", 2, "email")  # counts only: no keys, no content


def test_failed_storage_delete_propagates_so_the_transaction_rolls_back(patch_db):
    conn = patch_db(FakeConn(rows=[(1, "a", "app"), (2, "b", "app")]))
    with pytest.raises(RuntimeError):
        recordings.delete_speaker_recordings("S007", FakeStore(fail_on="b"))
    assert conn.rolled_back
    assert not any("INSERT INTO recording_deletions" in s[0] for s in conn.statements)


def test_deleting_a_speaker_with_no_recordings_is_still_logged(patch_db):
    conn = patch_db(FakeConn(rows=[]))
    assert recordings.delete_speaker_recordings("S999", FakeStore()) == 0
    assert any("INSERT INTO recording_deletions" in s[0] for s in conn.statements)


def test_delete_clears_both_buckets_with_the_right_store(patch_db):
    patch_db(FakeConn(rows=[(1, "a", "app"), (2, "r", "research")]))
    app_store, research_store = FakeStore(), FakeStore()
    deleted = recordings.delete_speaker_recordings(
        "S007", {"app": app_store, "research": research_store}
    )
    assert deleted == 2
    assert app_store.deleted == ["a"]
    assert research_store.deleted == ["r"]


def test_delete_refuses_when_research_bucket_is_not_configured(patch_db):
    conn = patch_db(FakeConn(rows=[(1, "a", "app"), (2, "r", "research")]))
    app_store = FakeStore()
    with pytest.raises(ValueError, match="research"):
        recordings.delete_speaker_recordings("S007", {"app": app_store})
    assert app_store.deleted == []  # nothing half-deleted
    assert not any(s[0].startswith("DELETE") for s in conn.statements)


@pytest.mark.parametrize(
    "uses, ok",
    [
        (["scorer_evaluation"], True),
        (["model_training"], True),
        (["reference_audio"], False),
        ([], False),
    ],
)
def test_research_recordings_need_research_consent(patch_db, uses, ok):
    patch_db(FakeConn())
    call = lambda: recordings.register_recording(  # noqa: E731
        "S007", "k", "v1", uses, purpose="research"
    )
    if ok:
        call()
    else:
        with pytest.raises(ValueError, match="research"):
            call()


def test_unknown_consent_use_is_rejected(patch_db):
    patch_db(FakeConn())
    with pytest.raises(ValueError, match="unknown consent"):
        recordings.register_recording("S007", "k", "v1", ["anything_goes"])


@pytest.mark.parametrize("bad", ["", "S 7", "../x", "a" * 65, "S7;DROP"])
def test_speaker_id_is_validated(bad):
    with pytest.raises(ValueError):
        recordings.delete_speaker_recordings(bad, FakeStore())


def test_register_requires_consent(patch_db):
    patch_db(FakeConn())
    with pytest.raises(ValueError, match="consent_version"):
        recordings.register_recording("S007", "k", "", ["scorer_evaluation"])


class FakeS3:
    def __init__(self, pages):
        self.pages = pages
        self.deleted = []

    def get_paginator(self, name):
        assert name == "list_object_versions"
        outer = self

        class P:
            def paginate(self, Bucket, Prefix):
                return iter(outer.pages)

        return P()

    def delete_objects(self, Bucket, Delete):
        self.deleted.extend(Delete["Objects"])
        return {}


def test_s3_store_removes_every_version_and_marker_of_the_exact_key():
    client = FakeS3(
        [
            {
                "Versions": [
                    {"Key": "rec/a.m4a", "VersionId": "v1"},
                    {"Key": "rec/a.m4a.bak", "VersionId": "other"},  # prefix match only
                ],
                "DeleteMarkers": [{"Key": "rec/a.m4a", "VersionId": "m1"}],
            }
        ]
    )
    recordings.S3RecordingStore("bucket", client).delete("rec/a.m4a")
    assert client.deleted == [
        {"Key": "rec/a.m4a", "VersionId": "v1"},
        {"Key": "rec/a.m4a", "VersionId": "m1"},
    ]


def test_confidence_score_must_be_a_probability_or_none(patch_db):
    conn = patch_db(FakeConn())
    with pytest.raises(ValueError):
        reviews.add_confidence_result("w", "translation", "m", 1.5)
    with pytest.raises(ValueError):
        reviews.add_confidence_result("w", "bogus", "m", 0.5)
    reviews.add_confidence_result("w", "translation", "m", None)  # unscored is allowed
    assert conn.statements[-1][1][5] is None


def test_correction_keeps_previous_value_and_does_not_edit_the_word(patch_db):
    conn = patch_db(FakeConn(one=("Hello", "sólam")))
    conn._one = ("Hello", "sólam")
    reviews.propose_correction("w", "rohingya_text", "salam", "R003", "spelling")
    insert = [s for s in conn.statements if "INSERT INTO reviewer_corrections" in s[0]][0]
    assert insert[1][2] == "sólam"  # previous_value captured
    assert not any("UPDATE vocabulary_words" in s[0] for s in conn.statements)


def test_deciding_twice_fails(patch_db):
    patch_db(FakeConn(one=None))
    with pytest.raises(LookupError):
        reviews.decide_correction(1, "accepted", "R001")
