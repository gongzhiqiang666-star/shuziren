"""Bounded producer ordering, loader failure propagation and writer cleanup."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import numpy as np

from recovered.image_clone_video_synthesizer import VideoSynthesizer


class PrefetchTests(unittest.TestCase):
    def run_case(self,fail=False):
        synth=object.__new__(VideoSynthesizer)
        synth.batch_size=2;synth.total_frames=7;synth.current_frame_position=0;synth.is_forward=True
        synth._closed=False;synth.executor=ThreadPoolExecutor(max_workers=2);synth.engine=None
        synth.extract_audio_features=lambda _:list(range(7))
        synth._load_single_frame=lambda index:(np.full((8,8,3),index,dtype=np.uint8),{})
        calls=[];written=[];closed=[];current=[0];peak=[0];lock=threading.Lock()
        def load(indices):
            with lock:current[0]+=1;peak[0]=max(peak[0],current[0])
            try:
                if fail and indices[0]==2:raise ValueError('bad source frame')
                calls.append(list(indices));return [synth._load_single_frame(i)[0] for i in indices],[{} for _ in indices]
            finally:
                with lock:current[0]-=1
        synth._load_batch_frames=load
        def process(images,metadata,features):
            self.assertEqual([int(image[0,0,0]) for image in images],features)
            return images
        synth._process_batch=process
        class Writer:
            def isOpened(self):return True
            def write(self,frame):written.append(int(frame[0,0,0]))
            def release(self):closed.append(True)
        with tempfile.TemporaryDirectory() as root,patch('recovered.image_clone_video_synthesizer.cv2.VideoWriter',return_value=Writer()),patch('recovered.image_clone_video_synthesizer._mux_video_audio') as mux:
            try:
                if fail:
                    with self.assertRaisesRegex(ValueError,'bad source frame'):
                        synth.process_single_file('audio',Path(root)/'out.mp4')
                    mux.assert_not_called()
                else:
                    synth.process_single_file('audio',Path(root)/'out.mp4')
                    self.assertEqual(written,list(range(7)))
                    self.assertEqual(calls,[[0,1],[2,3],[4,5],[6]])
                    mux.assert_called_once()
                self.assertEqual(closed,[True]);self.assertEqual(peak[0],1)
            finally:synth.close()

    def test_order_and_partial_final_batch(self):self.run_case()
    def test_loader_failure_closes_writer(self):self.run_case(True)
