"""In-memory, invented V1 facts. No application imports or source access."""
import copy
import math
import json
import time
from datetime import datetime, timezone

KINDS = ('front_preview', 'topdown_preview', 'imu_series')
SCENARIOS = ('mixed', 'empty', 'offline', 'scan-error', 'api-error', 'slow')
def stamp():
    return datetime.now(timezone.utc).isoformat()
class ApiError(Exception):
    def __init__(self, message, status=422):
        self.message, self.status = message, status

class Synthetic:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.media_sizes = {}
        self.reset('mixed')

    def reset(self, scenario):
        if scenario not in SCENARIOS:
            raise ApiError('Unknown scenario.')
        self.scenario, self.online = scenario, scenario != 'offline'
        self.last_tick = self.clock()
        self.generation, self.scanned, self.next_id = 1, stamp(), 1000
        self.recordings, self.jobs = [], []
        if scenario == 'empty':
            return
        names = ('Figure eight', 'Unprepared run', 'Processing run', 'Failed camera', 'Missing top camera', 'Damaged metadata', 'Zero duration', 'Long coverage gaps', 'Precision <test> & samples', 'Partial preparation')
        for i in range(24):
            duration = 0 if i == 6 else 120 if i == 7 else 12
            r = dict(id=i+1, name=names[i] if i < len(names) else f'Synthetic run {i+1:02}', folder_path=('Synthetic/Field/September', 'Synthetic/Lab/Bench', 'Synthetic/Inbox')[i % 3], start_time_ns=str(1772312400000000000+i*60000000000), duration_ns=str(duration*10**9), total_source_size_bytes=str(482344960+i*182345), storage_format='sqlite3', metadata_version=5, message_count='241', topic_count=12, ros_health='damaged' if i == 5 else 'readable', presentation_health='damaged' if i == 5 else 'readable', source_present=True, diagnostic=dict(code='synthetic_damaged', message='Synthetic metadata cannot be read.') if i == 5 else None, outputs=[], components=[dict(role='metadata', condition='readable', file_name='metadata.yaml', size_bytes='3821', mtime_ns='1772312400000000000', diagnostic=None), dict(role='rosbag', condition='readable', file_name='synthetic.db3', size_bytes='482341139', mtime_ns='1772312400000000000', diagnostic=None)])
            self.recordings.append(r)
            for kind in KINDS:
                state = 'not_requested' if i in (1, 2) or (i == 9 and kind != 'front_preview') else 'ready'
                diagnostic = None
                if i == 5 or (i == 4 and kind == 'topdown_preview'):
                    state = 'unavailable'
                    diagnostic = dict(code='topdown_video_unavailable' if i == 4 else 'synthetic_damaged', message='Synthetic source component unavailable.')
                r['outputs'].append(dict(kind=kind, state=state, diagnostic=diagnostic, artifact=self.artifact(r, kind) if state == 'ready' else None, job_id=None))
            if i == 3:
                self.finish(self.enqueue(r, 'topdown_preview'), 'failed')
            if i == 0:
                for kind in KINDS:
                    j = self.new_job(r, kind)
                    self.jobs.append(j)
                    self.finish(j, 'succeeded')
        self.prepare([3], list(KINDS))
        self.claim()
        for record in self.recordings:
            self.imu(record)

    def artifact(self, r, kind):
        aid = r['id']*10+KINDS.index(kind)+1
        start = 2 if r['id'] == 8 else 0
        end = min(int(r['duration_ns'])/1e9, start+12)
        return dict(id=aid, mime_type='application/json' if kind == 'imu_series' else 'video/mp4', size_bytes=str(self.media_sizes.get(kind,4096)), coverage_start_ns=str(int(start*1e9)), coverage_end_ns=str(int(end*1e9)), timestamp_provenance='ros_record_timestamp' if kind == 'imu_series' else 'csv_unix_timestamp' if kind == 'topdown_preview' else 'ros_image_header_affine_to_record_span', url=f"/api/recordings/{r['id']}/{kind.replace('_','-')}/{'data' if kind == 'imu_series' else 'media'}/{aid}")

    def record(self, rid):
        r = next((r for r in self.recordings if r['id'] == rid), None)
        if r is None:
            raise ApiError('Recording not found.', 404)
        return r

    def output(self, j):
        return next(o for o in self.record(j['recording_id'])['outputs'] if o['kind'] == j['kind'])

    def analysis(self, r):
        states = [o['state'] for o in r['outputs'] if not (o['kind'] == 'topdown_preview' and (o['diagnostic'] or {}).get('code') == 'topdown_video_unavailable')]
        return next((s for s in ('processing','queued','failed') if s in states), 'ready' if all(s == 'ready' for s in states) else 'not_planned')

    def new_job(self, r, kind):
        self.next_id += 1
        return dict(id=self.next_id, recording_id=r['id'], recording_name=r['name'], kind=kind, state='queued', queued_at=stamp(), started_at=None, finished_at=None, queued_age_ms=0, elapsed_ms=None, active_elapsed_ms=None, paused_ms=0, runtime_ms=None, diagnostic=None, output_size_bytes=None, queue_position=None, estimate=None, queue_estimate=None, control_state='none', execution_phase=None, control_revision=0, allowed_controls=[])

    def enqueue(self, r, kind):
        j = self.new_job(r, kind)
        self.jobs.append(j)
        self.output(j).update(state='queued', job_id=j['id'], artifact=None, diagnostic=None)
        return j

    def finish(self, j, state):
        j.update(state=state, finished_at=stamp(), runtime_ms=j['elapsed_ms'] or 0, control_state='none', allowed_controls=[], execution_phase=None)
        o = self.output(j)
        o.update(state={'succeeded':'ready','failed':'failed','canceled':'not_requested'}[state], artifact=None, job_id=j['id'])
        if state == 'succeeded':
            o['artifact'] = self.artifact(self.record(j['recording_id']), j['kind'])
            j['output_size_bytes'] = o['artifact']['size_bytes']
        if state == 'failed':
            j['diagnostic'] = dict(code='synthetic_validation', message='Synthetic camera validation failed. Retry exercises recovery.')
            o['diagnostic'] = j['diagnostic']

    def claim(self):
        if not self.online or any(j['state'] == 'running' for j in self.jobs):
            return
        j = next((j for j in self.jobs if j['state'] == 'queued'), None)
        if j:
            j.update(state='running', started_at=stamp(), elapsed_ms=0, active_elapsed_ms=0, execution_phase='processing')
            self.output(j)['state'] = 'processing'

    def tick(self):
        now = self.clock()
        delta = max(0, round((now-self.last_tick)*1000))
        self.last_tick = now
        for j in self.jobs:
            if j['state'] == 'queued':
                j['queued_age_ms'] += delta
            if j['state'] == 'running':
                j['elapsed_ms'] += delta
                if j['control_state'] == 'paused' or not self.online:
                    j['paused_ms'] += delta
                else:
                    j['active_elapsed_ms'] += delta
                    if j['active_elapsed_ms'] >= 18000:
                        self.finish(j, 'succeeded')
        self.claim()

    def view_job(self, j):
        item = copy.deepcopy(j)
        if j['state'] == 'running':
            item['allowed_controls'] = ['resume' if j['control_state'] == 'paused' else 'pause', 'cancel']
            item['estimate'] = dict(status='available', estimated_total_ms=18000, remaining_ms=max(0,18000-j['active_elapsed_ms']), method='synthetic', sample_count=3)
        elif j['state'] == 'queued':
            queue = [q for q in self.jobs if q['state'] == 'queued']
            item['queue_position'] = queue.index(j)+1
            item['allowed_controls'] = ['cancel','move_earlier','move_later']
            current = next((q for q in self.jobs if q['state'] == 'running'), None)
            available = self.online and not (current and current['control_state'] == 'paused')
            item['queue_estimate'] = dict(status='available' if available else 'unavailable', ready_in_ms=item['queue_position']*18000+(max(0,18000-current['active_elapsed_ms']) if current else 0) if available else None, method='synthetic' if available else None, sample_count=3 if available else None)
        return item

    def detail(self, r):
        return dict(copy.deepcopy(r), analysis_state=self.analysis(r))

    def catalog(self):
        rows = [self.detail(r) for r in self.recordings]
        folders = {}
        for r in rows:
            parts = r['folder_path'].split('/')
            for i, name in enumerate(parts):
                path = '/'.join(parts[:i+1])
                folder = folders.setdefault(path, dict(path=path, parent_path='/'.join(parts[:i]), name=name, direct_recording_count=0, descendant_recording_count=0))
                folder['descendant_recording_count'] += 1
                folder['direct_recording_count'] += int(i == len(parts)-1)
            for key in ('metadata_version','message_count','source_present','components'):
                r.pop(key)
            r['outputs'] = [{k:o[k] for k in ('kind','state','diagnostic')} for o in r['outputs']]
        damaged = sum(r['presentation_health'] == 'damaged' for r in rows)
        return dict(scan=dict(generation=self.generation, completed_at=self.scanned, duration_ms=17, counts=dict(recordings=len(rows), readable=len(rows)-damaged, damaged=damaged, missing=0, unsupported=0, uninspectable=0)), summary=dict(recordings=len(rows), damaged=damaged, **{s:sum(r['analysis_state'] == s for r in rows) for s in ('ready','processing','queued','failed')}), folders=list(folders.values()), recordings=rows)

    @staticmethod
    def ids(values):
        if not isinstance(values,list) or not 1 <= len(values) <= 100 or any(type(i) is not int or i <= 0 for i in values) or len(values) != len(set(values)):
            raise ApiError('Supply 1–100 unique positive IDs.')
        return values

    def prepare(self, ids, kinds):
        self.ids(ids)
        if not isinstance(kinds,list) or not 1 <= len(kinds) <= 3 or any(k not in KINDS for k in kinds) or len(set(kinds)) != len(kinds):
            raise ApiError('Choose a non-empty, unique set of supported outputs.')
        results = []
        for rid in ids:
            r = next((r for r in self.recordings if r['id'] == rid), None)
            if not r:
                results.append(dict(recording_id=rid, outcome='not_found', analysis_state='not_planned', outputs=[]))
                continue
            outputs = []
            for kind in KINDS:
                if kind not in kinds:
                    continue
                o = next(o for o in r['outputs'] if o['kind'] == kind)
                outcome = {'ready':'ready_reused','processing':'active_reused','queued':'active_reused','unavailable':'unavailable'}.get(o['state'])
                if outcome is None:
                    outcome = 'retry_queued' if o['state'] == 'failed' else 'queued'
                    self.enqueue(r, kind)
                outputs.append(dict(kind=kind, outcome=outcome, state=o['state'], diagnostic=o['diagnostic'], artifact_id=o['artifact']['id'] if o['artifact'] else None, job_id=o['job_id']))
            results.append(dict(recording_id=rid, outcome='resolved', analysis_state=self.analysis(r), outputs=outputs))
        return dict(recordings=results)

    def control(self, jid, action):
        j = next((j for j in self.jobs if j['id'] == jid), None)
        if j is None:
            raise ApiError('Job not found.',404)
        if action == 'retry':
            if j['state'] != 'failed':
                raise ApiError('Only failed jobs can be retried.',409)
            result = self.prepare([j['recording_id']],[j['kind']])['recordings'][0]['outputs'][0]
            return dict(result, recording_id=j['recording_id'])
        if action not in self.view_job(j)['allowed_controls']:
            raise ApiError('Job changed; refresh its available controls.',409)
        if action == 'cancel':
            self.finish(j,'canceled')
        else:
            j['control_state'] = 'paused' if action == 'pause' else 'none'
        j['control_revision'] += 1
        return dict(requested_job_id=jid,outcome='updated',job=self.view_job(j),server_time=stamp())

    def reorder(self, ids, direction):
        self.ids(ids)
        queue = [j for j in self.jobs if j['state'] == 'queued']
        if direction not in ('earlier','later') or any(i not in [j['id'] for j in queue] for i in ids):
            raise ApiError('Queue selection changed; refresh and try again.',409)
        indices = range(1,len(queue)) if direction == 'earlier' else range(len(queue)-2,-1,-1)
        step = -1 if direction == 'earlier' else 1
        for i in indices:
            if queue[i]['id'] in ids and queue[i+step]['id'] not in ids:
                queue[i],queue[i+step] = queue[i+step],queue[i]
        self.jobs = [j for j in self.jobs if j['state'] != 'queued']+queue
        return dict(items=[dict(requested_job_id=j['id'],outcome='updated',job=self.view_job(j),server_time=stamp()) for j in queue if j['id'] in ids],server_time=stamp())

    def listing(self, view):
        if view not in ('queued','failed','history','canceled'):
            raise ApiError('Unknown processing view.')
        state = 'succeeded' if view == 'history' else view
        rows = [j for j in self.jobs if j['state'] == state and (state != 'failed' or self.output(j)['job_id'] == j['id'] and self.output(j)['state'] == 'failed')]
        return rows if view == 'queued' else sorted(rows,key=lambda j:j['id'],reverse=True)

    def overview(self):
        current = next((j for j in self.jobs if j['state'] == 'running'),None)
        return dict(server_time=stamp(),worker_online=self.online,running_count=int(current is not None),current=self.view_job(current) if current else None,queued_count=len(self.listing('queued')),failed_count=len(self.listing('failed')),succeeded_count=len(self.listing('history')),canceled_count=len(self.listing('canceled')),queue=[self.view_job(j) for j in self.listing('queued')[:25]],recommended_poll_interval_ms=1000,current_stage=1 if current else 0,current_stage_count=3 if current else 0)

    def imu(self,r):
        o = next(o for o in r['outputs'] if o['kind'] == 'imu_series')
        if o['state'] != 'ready':
            return dict(state=o['state'],global_duration_ns=r['duration_ns'],artifact=None,diagnostic=o['diagnostic'],poll_after_ms=1000),None
        art = o['artifact']
        start,end = int(art['coverage_start_ns']),int(art['coverage_end_ns'])
        samples = [[str(start+(end-start)*i//240),*[round(math.sin(i/(12+c*3))+(9.81 if c == 5 else 0),5) for c in range(6)]] for i in range(241)]
        if end == start:
            samples = samples[:1]
        else:
            samples[40][1] = None
            samples.insert(121,[samples[120][0],.75,.5,.25,0,0,9.81])
        series = []
        for c in range(6):
            component = ('angular_velocity' if c < 3 else 'linear_acceleration')+'.'+'xyz'[c%3]
            values = [s[c+1] for s in samples if s[c+1] is not None]
            units = 'rad/s' if c < 3 else 'm/s²'
            series.append(dict(id=component.replace('.','_'),component=component,display_label=f'{component} ({units})',units=units,column_index=c+1,finite_sample_count=str(len(values)),non_finite_sample_count=str(len(samples)-len(values)),minimum_value=min(values),maximum_value=max(values),available=True))
        manifest = dict(mime_type='application/json',size_bytes='4096',coverage_start_ns=str(start),coverage_end_ns=str(end),timestamp_provenance='ros_record_timestamp',bounds='measured',topic='/synthetic/imu',default_series_id='angular_velocity_z',source_sample_count=str(len(samples)),delivered_sample_count=str(len(samples)),duplicate_timestamp_count='1' if end > start else '0',series=series,reduction_method='none',warnings=[],data_url=art['url'])
        payload = dict(schema_version=2,samples=samples)
        manifest['size_bytes'] = str(len(json.dumps(payload).encode()))
        o['artifact']['size_bytes'] = manifest['size_bytes']
        return dict(state='ready',global_duration_ns=r['duration_ns'],artifact=manifest,diagnostic=None,poll_after_ms=None),payload
