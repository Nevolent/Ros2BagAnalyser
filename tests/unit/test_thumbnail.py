from dataclasses import replace
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import av
import pytest

from conftest import create_rosbag_database, inventory
from rosbag_analyser.artifact_store import ArtifactStore, ArtifactStoreError
from rosbag_analyser.catalog.metadata import TopicFact
from rosbag_analyser.catalog.paths import source_file_identity
from rosbag_analyser.front_preview import FrontSourceDescriptor
from rosbag_analyser.job_control import JobCanceled
from rosbag_analyser.persistence.processing_repository import JobRecord
from rosbag_analyser.processors.front_preview import DecodedImage, FrontPreviewProcessingError
from rosbag_analyser.processors.thumbnail import ThumbnailProcessor
from rosbag_analyser.thumbnail import THUMBNAIL_POLICY, thumbnail_cache_identity
from rosbag_analyser.worker import SerialWorker


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    database = root / "bag.db3"
    create_rosbag_database(database)
    with sqlite3.connect(database) as connection:
        connection.execute("INSERT INTO topics VALUES (1, '/camera/front', 'sensor_msgs/msg/Image', 'cdr', '')")
        # Midpoint=50; select 60 and the last message at its duplicate timestamp.
        for index, timestamp in enumerate([10, 20, 60, 60, 90], 1):
            connection.execute("INSERT INTO messages VALUES (?, 1, ?, ?)", (index, timestamp, bytes([index])))
    identity = source_file_identity(database.stat())
    topic = TopicFact('/camera/front', 'sensor_msgs/msg/Image', 'cdr', 5)
    descriptor = FrontSourceDescriptor(1, 'bag', root / 'metadata.yaml', database,
                                       identity, identity, 0, 100, topic, 'a' * 64)
    decoded = []

    def decode(data):
        decoded.append(data[0])
        return DecodedImage(640, 360, 'bgr8', 1922, bytes([data[0], 0, 255] * 640 + [0, 0]) * 360)

    return SimpleNamespace(root=root, descriptor=descriptor, decoded=decoded,
                           processor=ThumbnailProcessor(decode))


def test_five_frames_share_scans_and_duplicate_payloads_preserving_source_and_aspect(source, tmp_path):
    before = inventory(source.root)
    output = tmp_path / 'thumbnail.png'
    result = source.processor.process(source.descriptor, output)
    assert source.decoded == [1, 4, 5]
    assert result == {'topic': '/camera/front', 'record_timestamp_ns': '60',
                      'record_timestamps_ns': ['60', '60', '60', '90', '90'],
                      'coverage_ns': 60, 'width': 2400, 'height': 270,
                      'frame_width': 480, 'frame_count': 5}
    with av.open(str(output)) as container:
        frames = list(container.decode(video=0))
    assert len(frames) == 1
    assert (frames[0].width, frames[0].height) == (2400, 270)
    assert inventory(source.root) == before


def test_monochrome_stream_is_skipped_before_default_colour_camera(source, tmp_path):
    with sqlite3.connect(source.descriptor.database_path) as connection:
        connection.execute("INSERT INTO topics VALUES (2, '/ouster/image', 'sensor_msgs/msg/Image', 'cdr', '')")
        connection.execute("INSERT INTO messages VALUES (6, 2, 5, ?)", (bytes([6]),))
    descriptor = replace(source.descriptor,
                         database_identity=source_file_identity(source.descriptor.database_path.stat()),
                         topics=(TopicFact('/ouster/image', 'sensor_msgs/msg/Image', 'cdr', 1), source.descriptor.topic))
    colour_decode = source.processor.image_decoder
    source.processor.image_decoder = lambda data: DecodedImage(1, 1, 'mono8', 1, b'x') if data == bytes([6]) else colour_decode(data)
    assert source.processor.process(descriptor, tmp_path / 'thumbnail.png')['topic'] == '/camera/front'
    assert source.decoded == [1, 4, 5]


def test_midpoint_selection_handles_unordered_rows_and_duplicate_endpoints(source, tmp_path):
    with sqlite3.connect(source.descriptor.database_path) as connection:
        connection.execute("DELETE FROM messages")
        for message_id, timestamp in ((1, 90), (2, 60), (3, 10), (4, 60), (5, 10)):
            connection.execute("INSERT INTO messages VALUES (?, 1, ?, ?)",
                               (message_id, timestamp, bytes([message_id])))
    descriptor = replace(source.descriptor, database_identity=source_file_identity(source.descriptor.database_path.stat()))
    before = inventory(source.root)
    result = source.processor.process(descriptor, tmp_path / 'thumbnail.png')
    assert source.decoded == [5, 4, 1]
    assert result['record_timestamp_ns'] == '60'
    assert inventory(source.root) == before


def test_large_metadata_scan_can_cancel_before_reading_image_payloads(source, tmp_path):
    with sqlite3.connect(source.descriptor.database_path) as connection:
        connection.executemany("INSERT INTO messages VALUES (?, 99, ?, ?)",
                               ((100 + i, i, b'unrelated') for i in range(5000)))
    descriptor = replace(source.descriptor, database_identity=source_file_identity(source.descriptor.database_path.stat()))

    class Control:
        calls = 0

        def checkpoint(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 4:
                raise JobCanceled('cancelled')

    before = inventory(source.root)
    with pytest.raises(JobCanceled):
        source.processor.process(descriptor, tmp_path / 'thumbnail.png', control=Control())
    assert source.decoded == []
    assert not (tmp_path / 'thumbnail.png').exists()
    assert inventory(source.root) == before


def test_expired_metadata_query_reports_timeout_instead_of_database_failure(source, tmp_path, monkeypatch):
    import rosbag_analyser.processors.thumbnail as module
    with sqlite3.connect(source.descriptor.database_path) as connection:
        connection.executemany("INSERT INTO messages VALUES (?, 99, ?, ?)",
                               ((100 + i, i, b'x') for i in range(5000)))
    descriptor = replace(source.descriptor, database_identity=source_file_identity(source.descriptor.database_path.stat()))
    calls = 0

    def clock():
        nonlocal calls
        calls += 1
        return (calls - 1) * 31

    monkeypatch.setattr(module.time, 'monotonic', clock)
    with pytest.raises(FrontPreviewProcessingError) as captured:
        source.processor.process(descriptor, tmp_path / 'thumbnail.png')
    assert captured.value.code == 'thumbnail_query_timeout'


def test_source_changed_or_symlinked_is_rejected(source, tmp_path):
    source.descriptor.database_path.touch()
    with pytest.raises(FrontPreviewProcessingError, match='changed'):
        source.processor.process(source.descriptor, tmp_path / 'thumbnail.png')
    link = source.root / 'link.db3'
    link.symlink_to(source.descriptor.database_path)
    with pytest.raises(FrontPreviewProcessingError, match='opened safely'):
        source.processor.process(replace(source.descriptor, database_path=link), tmp_path / 'thumbnail.png')


def test_cancel_before_payload_read(source, tmp_path):
    class Control:
        def checkpoint(self, *args, **kwargs):
            raise JobCanceled('cancelled')
    with pytest.raises(JobCanceled):
        source.processor.process(source.descriptor, tmp_path / 'thumbnail.png', control=Control())
    assert source.decoded == []


@pytest.fixture
def worker(source, tmp_path):
    derived = tmp_path / 'derived'
    derived.mkdir()
    store = ArtifactStore(derived, Path('ffmpeg'), Path('ffprobe'), 'thumbnail')
    class Repository:
        completed = []
        failures = []
        def complete_job(self, job_id, artifact):
            self.completed.append(artifact)
        def fail_job(self, job_id, code, message):
            self.failures.append(code)
    repository = Repository()
    resolver = SimpleNamespace(resolve=lambda recording_id: SimpleNamespace(descriptor=source.descriptor))
    instance = SerialWorker(repository, resolver, None, store, '', '',
                            thumbnail_processor=source.processor, thumbnail_artifact_store=store)
    now = datetime.now(timezone.utc)
    job = JobRecord(8, 1, 'thumbnail', thumbnail_cache_identity(source.descriptor.cache_identity),
                    'running', now, now, None, None, None)
    return SimpleNamespace(instance=instance, repository=repository, job=job, store=store, derived=derived)


def test_worker_publishes_validated_identity_bound_thumbnail_without_preview(worker, source):
    before = inventory(source.root)
    worker.instance._run_job(worker.job)
    assert worker.repository.failures == []
    artifact = worker.repository.completed[0]
    assert artifact.manifest['processor_version'] == THUMBNAIL_POLICY
    assert artifact.mime_type == 'image/png'
    assert artifact.coverage_start_ns == artifact.coverage_end_ns == 60
    opened = worker.store.open_thumbnail(artifact.output_relative_path, artifact.size_bytes,
                                         artifact.cache_identity, artifact.manifest)
    os.close(opened.descriptor)
    assert inventory(source.root) == before
    assert not list(worker.store.work_root.iterdir())


def test_thumbnail_publication_finalizes_timestamp_without_accepting_changed_bytes(worker, monkeypatch):
    import rosbag_analyser.thumbnail as module
    original = module.validate_thumbnail

    def finalize(data, manifest):
        original(data, manifest)
        path = next(worker.store.work_root.glob('*/thumbnail.png'))
        details = path.stat()
        os.utime(path, ns=(details.st_atime_ns, details.st_mtime_ns + 1_000_000_000))

    monkeypatch.setattr(module, 'validate_thumbnail', finalize)
    worker.instance._run_job(worker.job)
    assert worker.repository.failures == []
    artifact = worker.repository.completed[0]
    path = worker.derived / artifact.output_relative_path
    assert artifact.manifest['output']['file_identity']['mtime_ns'] == path.stat().st_mtime_ns
    monkeypatch.setattr(module, 'validate_thumbnail', original)
    opened = worker.store.open_thumbnail(artifact.output_relative_path, artifact.size_bytes,
                                         artifact.cache_identity, artifact.manifest)
    os.close(opened.descriptor)


def test_invalid_replacement_and_changed_source_preserve_valid_output(worker, source):
    worker.instance._run_job(worker.job)
    artifact = worker.repository.completed[0]
    path = worker.derived / artifact.output_relative_path
    before = path.read_bytes(), path.stat()
    workspace = worker.store.create_workspace(9)
    (workspace / 'thumbnail.png').write_bytes(b'not a PNG')
    with pytest.raises(ArtifactStoreError):
        worker.store.publish_thumbnail(workspace, 9, artifact.cache_identity, artifact.manifest, replace_conflicting=True)
    assert (path.read_bytes(), path.stat()) == before
    source.descriptor = replace(source.descriptor, cache_identity='b' * 64)
    worker.instance._run_job(worker.job)
    assert worker.repository.failures == ['thumbnail_inputs_changed']
    assert len(worker.repository.completed) == 1
    assert (path.read_bytes(), path.stat()) == before
    worker.store.clean_workspace(workspace, 9)


def test_same_size_payload_tampering_fails_delivery(worker):
    worker.instance._run_job(worker.job)
    artifact = worker.repository.completed[0]
    path = worker.derived / artifact.output_relative_path
    data = bytearray(path.read_bytes())
    data[-10] ^= 1
    path.write_bytes(data)
    with pytest.raises(ArtifactStoreError):
        worker.store.open_thumbnail(artifact.output_relative_path, artifact.size_bytes,
                                    artifact.cache_identity, artifact.manifest)


def test_catalog_reuses_validation_only_for_unchanged_file_and_manifest(worker, monkeypatch):
    import rosbag_analyser.thumbnail as thumbnail_module
    worker.instance._run_job(worker.job)
    artifact = worker.repository.completed[0]
    arguments = (artifact.output_relative_path, artifact.size_bytes, artifact.cache_identity, artifact.manifest)
    original = thumbnail_module.validate_thumbnail
    validated = []
    def validate(data, manifest):
        validated.append(True)
        original(data, manifest)
    monkeypatch.setattr(thumbnail_module, 'validate_thumbnail', validate)
    worker.store.validate_thumbnail_artifact(*arguments)
    worker.store.validate_thumbnail_artifact(*arguments)
    assert len(validated) == 1
    opened = worker.store.open_thumbnail(*arguments)
    os.close(opened.descriptor)
    assert len(validated) == 1
    path = worker.derived / artifact.output_relative_path
    stamp = path.stat()
    data = bytearray(path.read_bytes())
    data[-10] ^= 1
    path.write_bytes(data)
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    with pytest.raises(ArtifactStoreError):
        worker.store.validate_thumbnail_artifact(*arguments)
    assert len(validated) == 2


def test_regular_stream_samples_five_sixths_with_only_two_header_scans(source, tmp_path, monkeypatch):
    import rosbag_analyser.processors.thumbnail as module
    with sqlite3.connect(source.descriptor.database_path) as connection:
        connection.execute('DELETE FROM messages')
        connection.executemany('INSERT INTO messages VALUES (?, 1, ?, ?)',
                               [(i + 1, i * 6, bytes([i + 1])) for i in range(101)])
    descriptor = replace(source.descriptor, database_identity=source_file_identity(source.descriptor.database_path.stat()))
    scans = []
    original = module._metadata_rows
    def metadata(*args):
        scans.append(True)
        yield from original(*args)
    monkeypatch.setattr(module, '_metadata_rows', metadata)
    before = inventory(source.root)
    result = source.processor.process(descriptor, tmp_path / 'thumbnail.png')
    assert len(scans) == 2
    assert result['record_timestamps_ns'] == ['102', '204', '300', '402', '504']
    assert len(source.decoded) == 6  # Eligibility plus five chosen payloads.
    assert inventory(source.root) == before
