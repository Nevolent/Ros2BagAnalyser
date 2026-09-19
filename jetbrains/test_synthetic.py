import unittest
from synthetic import Synthetic, ApiError, KINDS

class SyntheticTests(unittest.TestCase):
    def setUp(self):
        self.now=0
        self.s=Synthetic(lambda:self.now)
    def advance(self,seconds):
        self.now+=seconds
        self.s.tick()
    def test_catalog_read_does_not_scan_or_enqueue(self):
        before=(self.s.generation,len(self.s.jobs))
        self.s.catalog();self.s.catalog()
        self.assertEqual(before,(self.s.generation,len(self.s.jobs)))
        self.assertEqual(len(self.s.catalog()['recordings']),24)
    def test_prepare_idempotent_and_unavailable_is_not_job(self):
        before=len(self.s.jobs)
        self.s.prepare([2,6],list(KINDS))
        self.assertEqual(len(self.s.jobs),before+3)
        self.s.prepare([2,6],list(KINDS))
        self.assertEqual(len(self.s.jobs),before+3)
        self.assertEqual(self.s.analysis(self.s.record(6)),'not_planned')
    def test_ready_reuse_and_optional_camera(self):
        before=len(self.s.jobs)
        result=self.s.prepare([1],list(KINDS))
        self.assertTrue(all(o['outcome']=='ready_reused' for o in result['recordings'][0]['outputs']))
        self.assertEqual(len(self.s.jobs),before)
        self.assertEqual(self.s.analysis(self.s.record(5)),'ready')
    def test_pause_resume_cancel_releases_worker(self):
        current=self.s.overview()['current']
        self.advance(2)
        self.s.control(current['id'],'pause')
        self.advance(20)
        paused=self.s.overview()['current']
        self.assertEqual(paused['active_elapsed_ms'],2000)
        self.assertEqual(paused['paused_ms'],20000)
        self.s.control(current['id'],'cancel')
        self.advance(1)
        self.assertNotEqual(self.s.overview()['current']['id'],current['id'])
        self.assertEqual(self.s.overview()['current']['control_state'],'none')
    def test_retry_is_idempotent(self):
        failed=self.s.listing('failed')[0]
        one=self.s.control(failed['id'],'retry')
        two=self.s.control(failed['id'],'retry')
        self.assertEqual(one['job_id'],two['job_id'])
        self.assertFalse(self.s.listing('failed'))
    def test_reorder_is_real_and_atomic(self):
        queue=self.s.listing('queued')
        last=queue[-1]['id']
        self.s.reorder([last],'earlier')
        self.assertEqual(self.s.listing('queued')[0]['id'],last)
        snapshot=[j['id'] for j in self.s.jobs]
        with self.assertRaises(ApiError):self.s.reorder([last,999999],'earlier')
        self.assertEqual(snapshot,[j['id'] for j in self.s.jobs])
        self.s.control(self.s.overview()['current']['id'],'cancel');self.advance(1)
        self.assertEqual(self.s.overview()['current']['id'],last)
    def test_worker_advances_without_browser_reads(self):
        initial=self.s.overview()['current']['id']
        self.advance(19)
        self.assertNotEqual(initial,self.s.overview()['current']['id'])
        self.advance(19);self.advance(19)
        self.assertEqual(self.s.analysis(self.s.record(3)),'ready')
        self.assertEqual(self.s.overview()['running_count'],0)
    def test_schema_two_null_duplicate_and_coverage(self):
        metadata,payload=self.s.imu(self.s.record(8))
        self.assertEqual(len(metadata['artifact']['series']),6)
        self.assertEqual(payload['schema_version'],2)
        self.assertEqual(payload['samples'][120][0],payload['samples'][121][0])
        self.assertIsNone(payload['samples'][40][1])
        self.assertEqual(metadata['artifact']['coverage_start_ns'],'2000000000')
        self.assertEqual(metadata['artifact']['coverage_end_ns'],'14000000000')
    def test_validation(self):
        for ids in ([],[0],[True],[1,1],list(range(1,102))):
            with self.assertRaises(ApiError):self.s.prepare(ids,list(KINDS))
        with self.assertRaises(ApiError):self.s.prepare([1],[])
    def test_empty_offline(self):
        self.s.reset('empty');self.assertFalse(self.s.catalog()['recordings'])
        self.s.reset('offline');self.advance(100)
        self.assertEqual(self.s.overview()['running_count'],0)
        self.assertEqual(self.s.overview()['queued_count'],3)
if __name__=='__main__':unittest.main()
