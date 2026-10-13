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
from rosbag_analyser.persistence.processing_repository import JobRecord, ProcessingSourceRecord, ProcessingComponent
from rosbag_analyser.processors.front_preview import DecodedImage, FrontPreviewProcessingError
from rosbag_analyser.processors.thumbnail import ThumbnailProcessor
from rosbag_analyser.thumbnail import THUMBNAIL_POLICY, thumbnail_cache_identity, thumbnail_source_identity
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


def test_six_frames_share_scans_and_duplicate_payloads_preserving_source_and_aspect(source, tmp_path):
    before = inventory(source.root)
    output = tmp_path / 'thumbnail.png'
    result = source.processor.process(source.descriptor, output)
    assert source.decoded == [1, 4, 5]
    assert result == {'topic': '/camera/front', 'record_timestamp_ns': '60',
                      'record_timestamps_ns': ['60', '60', '60', '60', '90', '90'],
                      'frame_times_seconds': [6e-8, 6e-8, 6e-8, 6e-8, 9e-8, 9e-8],
                      'coverage_ns': 60, 'width': 2688, 'height': 252,
                      'frame_width': 448, 'frame_count': 6}
    with av.open(str(output)) as container:
        frames = list(container.decode(video=0))
    assert len(frames) == 1
    assert (frames[0].width, frames[0].height) == (2688, 252)
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
    record = ProcessingSourceRecord(1, 'bag', 0, 100, 'readable',
        ProcessingComponent('metadata.yaml', 1, 1, 'readable'),
        ProcessingComponent('bag.db3', 1, 1, 'readable'))
    repository.get_source = lambda recording_id: record
    repository.get_current_outputs = lambda ids: ()
    resolver = SimpleNamespace(resolve=lambda recording_id, **kwargs: SimpleNamespace(descriptor=source.descriptor, diagnostic=None),
        _resolve_component=lambda component: (source.descriptor.metadata_path, source.descriptor.metadata_identity)
        if component is record.metadata else (source.descriptor.database_path, source.descriptor.database_identity))
    instance = SerialWorker(repository, resolver, None, store, '', '',
                            thumbnail_processor=source.processor, thumbnail_artifact_store=store)
    now = datetime.now(timezone.utc)
    source_identity = thumbnail_source_identity(record, source.descriptor.metadata_identity, source.descriptor.database_identity)
    job = JobRecord(8, 1, 'thumbnail', thumbnail_cache_identity(source_identity),
                    'running', now, now, None, None, None)
    return SimpleNamespace(instance=instance, repository=repository, job=job, store=store, derived=derived)


def test_worker_publishes_validated_identity_bound_thumbnail_without_preview(worker, source):
    before = inventory(source.root)
    worker.instance._run_job(worker.job)
    assert worker.repository.failures == []
    artifact = worker.repository.completed[0]
    assert artifact.manifest['processor_version'] == THUMBNAIL_POLICY
    assert artifact.mime_type == 'image/png'
    assert (artifact.coverage_start_ns, artifact.coverage_end_ns) == (60, 90)
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
    source.descriptor = replace(source.descriptor, database_identity=replace(source.descriptor.database_identity,
                                mtime_ns=source.descriptor.database_identity.mtime_ns + 1))
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


def test_regular_stream_samples_six_sevenths_with_only_two_header_scans(source, tmp_path, monkeypatch):
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
    assert result['record_timestamps_ns'] == ['90', '174', '258', '342', '432', '516']
    assert len(source.decoded) == 7  # Eligibility plus six chosen payloads.
    assert inventory(source.root) == before


def test_one_valid_frame_survives_damaged_samples_and_is_valid_for_ai(worker, source):
    from rosbag_analyser.thumbnail import thumbnail_frames
    original = source.processor.image_decoder
    def only_one(data):
        if data != bytes([1]):
            raise FrontPreviewProcessingError('front_frame_invalid', 'Damaged fixture frame.')
        return original(data)
    source.processor.image_decoder = only_one
    worker.instance._run_job(worker.job)
    assert not worker.repository.failures
    artifact = worker.repository.completed[0]
    assert artifact.manifest['output']['frame_count'] == 1
    opened = worker.store.open_thumbnail(artifact.output_relative_path, artifact.size_bytes, artifact.cache_identity, artifact.manifest)
    try:
        images, times = thumbnail_frames(opened.descriptor, artifact.manifest)
        assert len(images) == len(times) == 1
    finally:
        os.close(opened.descriptor)


def test_prepared_mp4_supplies_six_frames_without_reading_bag_payloads(worker, source, tmp_path):
    from rosbag_analyser.persistence.processing_repository import ArtifactRecord
    import numpy as np
    import hashlib
    from rosbag_analyser.thumbnail import thumbnail_frames
    front_store = ArtifactStore(worker.derived, Path('/usr/bin/ffmpeg'), Path('/usr/bin/ffprobe'))
    workspace = front_store.create_workspace(90)
    path = workspace / 'preview.mp4'
    with av.open(str(path), 'w') as container:
        stream = container.add_stream('libx264', rate=10)
        stream.width, stream.height, stream.pix_fmt = 96, 54, 'yuv420p'
        for index in range(20):
            frame = av.VideoFrame.from_ndarray(np.full((54, 96, 3), index * 10, dtype=np.uint8), format='rgb24')
            frame.pts = index
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
    details = path.stat()
    manifest = {'artifact_kind': 'front_preview', 'cache_identity': source.descriptor.cache_identity,
        'output': {'file_name': 'preview.mp4', 'size_bytes': details.st_size,
        'file_identity': {'device_id': details.st_dev, 'inode': details.st_ino, 'mtime_ns': details.st_mtime_ns}}}
    published = front_store.publish(workspace, 90, source.descriptor.cache_identity, manifest)
    artifact = ArtifactRecord(90, 1, 'front_preview', source.descriptor.cache_identity,
        published.output_relative_path, 'video/mp4', published.size_bytes, 2_000_000_000, 4_000_000_000,
        manifest, datetime.now(timezone.utc))
    worker.instance.artifact_store = front_store
    worker.repository.get_current_outputs = lambda ids: (SimpleNamespace(target=SimpleNamespace(kind='front_preview'), artifact=artifact),)
    source.processor.image_decoder = lambda data: pytest.fail('Prepared MP4 must avoid source payload reads')
    worker.instance._run_job(worker.job)
    assert not worker.repository.failures and source.decoded == []
    thumbnail = worker.repository.completed[0]
    assert thumbnail.manifest['output']['frame_count'] == 6
    opened = worker.store.open_thumbnail(thumbnail.output_relative_path, thumbnail.size_bytes, thumbnail.cache_identity, thumbnail.manifest)
    try:
        images, times = thumbnail_frames(opened.descriptor, thumbnail.manifest)
        assert len(images) == 6 and times == sorted(times) and min(times) >= 2
    finally:
        os.close(opened.descriptor)


def test_companion_video_without_raw_camera_supplies_fallback_thumbnail(worker, tmp_path):
    import numpy as np
    path = tmp_path / 'camera.avi'
    with av.open(str(path), 'w') as container:
        stream = container.add_stream('mpeg4', rate=10)
        stream.width, stream.height, stream.pix_fmt = 96, 54, 'yuv420p'
        frame = av.VideoFrame.from_ndarray(np.full((54, 96, 3), 80, dtype=np.uint8), format='rgb24')
        frame.pts = 0
        for packet in stream.encode(frame) + stream.encode(None):
            container.mux(packet)
    before = path.read_bytes(), source_file_identity(path.stat())
    output = tmp_path / 'thumbnail.png'
    result = worker.instance._thumbnail_result(worker.job,
        ('a' * 64, None, (path, before[1]), SimpleNamespace(start_time_ns=0)), output, None)
    assert result['topic'] == 'companion-video' and 1 <= result['frame_count'] <= 6
    assert output.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
    assert (path.read_bytes(), source_file_identity(path.stat())) == before
