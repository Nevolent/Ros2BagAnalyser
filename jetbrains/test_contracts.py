"""Compare the experiment HTTP responses with the existing application schemas.
Run using the project's existing Python environment; no application is started.
"""
import json
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from rosbag_analyser.api import v1_schemas as s
from rosbag_analyser.api.imu_series_schemas import ImuSeriesResponse
ORIGIN='http://127.0.0.1:4174'
def call(path,body=None):
    request=Request(ORIGIN+path,data=None if body is None else json.dumps(body).encode(),headers={} if body is None else {'Content-Type':'application/json'})
    with urlopen(request) as response:return json.load(response)
class ContractTests(unittest.TestCase):
    def setUp(self):call('/__experiment/scenario',{'scenario':'mixed'})
    def test_catalog_detail_rescan_and_prepare(self):
        catalog=s.CatalogResponse.model_validate(call('/api/v1/catalog'))
        self.assertEqual(catalog.summary.recordings,24)
        s.RecordingDetailResponse.model_validate(call('/api/v1/recordings/1'))
        s.RescanResponse.model_validate(call('/api/v1/catalog/rescan',{}))
        response=s.PrepareSelectedResponse.model_validate(call('/api/v1/recordings/prepare',{'recording_ids':[2,6],'output_kinds':['front_preview','imu_series']}))
        self.assertEqual(response.recordings[1].outputs[0].outcome,'unavailable')
    def test_controls_and_processing_views(self):
        overview=s.ProcessingOverviewResponse.model_validate(call('/api/v1/processing/overview'))
        for view in ('queued','failed','history','canceled'):
            s.ProcessingJobsResponse.model_validate(call('/api/v1/processing/jobs?view='+view+'&limit=100'))
        jid=overview.current.id
        for action in ('pause','resume','cancel'):
            s.ControlResponse.model_validate(call(f'/api/v1/processing/jobs/{jid}/{action}',{}))
        failed=call('/api/v1/processing/jobs?view=failed')['items'][0]['id']
        s.RetryResponse.model_validate(call(f'/api/v1/processing/jobs/{failed}/retry',{}))
        s.BulkRetryResponse.model_validate(call('/api/v1/processing/jobs/retry',{'job_ids':[failed]}))
        queue=call('/api/v1/processing/jobs?view=queued')['items']
        ids=[queue[-1]['id']]
        s.BulkControlResponse.model_validate(call('/api/v1/processing/jobs/reorder',{'job_ids':ids,'direction':'earlier'}))
        s.BulkControlResponse.model_validate(call('/api/v1/processing/jobs/cancel',{'job_ids':ids}))
    def test_imu_and_identity_bound_ranges(self):
        imu=ImuSeriesResponse.model_validate(call('/api/recordings/1/imu-series'))
        self.assertEqual(len(imu.artifact.series),6)
        self.assertEqual(call(imu.artifact.data_url)['schema_version'],2)
        detail=call('/api/v1/recordings/1')
        media=detail['outputs'][0]['artifact']['url']
        with urlopen(Request(ORIGIN+media,headers={'Range':'bytes=0-15'})) as response:
            self.assertEqual(response.status,206);self.assertEqual(len(response.read()),16)
            self.assertTrue(response.headers['Content-Range'].startswith('bytes 0-15/'))
        with urlopen(Request(ORIGIN+media,method='HEAD')) as response:
            self.assertEqual(response.status,200);self.assertEqual(response.read(),b'')
        with self.assertRaises(HTTPError) as result:urlopen(ORIGIN+media+'0')
        self.assertEqual(result.exception.code,409)
        with self.assertRaises(HTTPError) as result:urlopen(Request(ORIGIN+media,headers={'Range':'bytes=999999999-'}))
        self.assertEqual(result.exception.code,416)
    def test_failure_retains_catalog_and_bounds(self):
        call('/__experiment/scenario',{'scenario':'scan-error'})
        before=call('/api/v1/catalog')['scan']
        with self.assertRaises(HTTPError) as result:call('/api/v1/catalog/rescan',{})
        self.assertEqual(result.exception.code,503)
        self.assertEqual(call('/api/v1/catalog')['scan'],before)
        with self.assertRaises(HTTPError):call('/api/v1/recordings/prepare',{'recording_ids':[1,1]})
        with self.assertRaises(HTTPError):urlopen(ORIGIN+'/../README.md')
    def tearDown(self):call('/__experiment/scenario',{'scenario':'mixed'})
if __name__=='__main__':unittest.main()
