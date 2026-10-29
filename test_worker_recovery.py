"""Exercise actual spawned child timeout, cancellation and subsequent recovery."""
import multiprocessing
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
import analysis_jobs
import data_identity,settings


def fixture_task(kind,params):
    if kind=='slow':time.sleep(60)
    return {'finished':True}


def fixture_worker(folder):
    import worker,settings
    root=Path(folder)
    settings.SETTINGS=replace(settings.SETTINGS,state_db=root/'state.sqlite3',db=root/'data.sqlite3',geography_dir=root/'geo',job_timeout_seconds=10)
    worker.main(executor=fixture_task)


class WorkerRecovery(unittest.TestCase):
    def test_timeout_and_cancellation_terminate_child_then_recover(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'data.sqlite3').touch();(root/'geo').mkdir()
            path=root/'state.sqlite3';process=multiprocessing.get_context('spawn').Process(target=fixture_worker,args=(folder,))
            process.start()
            identity=data_identity.identity(root/'data.sqlite3',root/'geo',settings.SETTINGS.release_id,settings.SETTINGS.cutoff)
            def enqueue(kind,params):return analysis_jobs.enqueue(path,kind,params,identity,settings.METHOD_VERSION,10)
            def until(job,states):
                deadline=time.monotonic()+40
                while time.monotonic()<deadline:
                    current=analysis_jobs.get(path,job['id'])
                    if current['status'] in states:return current
                    self.assertTrue(process.is_alive());time.sleep(.1)
                self.fail('Worker did not reach expected state')
            try:
                stale=analysis_jobs.enqueue(path,'fast',{'old':True},'old-data','old-method',10)
                self.assertIn('datos han cambiado',until(stale,{'failed'})['error'])
                timed=until(enqueue('slow',{'n':1}),{'failed'})
                self.assertIn('Tiempo máximo',timed['error'])
                cancelled=enqueue('slow',{'n':2});until(cancelled,{'running'})
                analysis_jobs.cancel(path,cancelled['id'])
                fast=until(enqueue('fast',{}),{'complete'})
                self.assertEqual(fast['result'],{'finished':True})
                self.assertEqual(analysis_jobs.get(path,cancelled['id'])['status'],'cancelled')
            finally:
                process.terminate();process.join(timeout=10)
                if process.is_alive():process.kill();process.join()
                # The calculation process watches the parent even on Windows forced termination.
                time.sleep(1.2)


if __name__=='__main__':unittest.main()
