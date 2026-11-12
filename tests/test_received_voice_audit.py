from fractions import Fraction
from pathlib import Path
import tempfile
import unittest
import wave
import av
import numpy as np
from scipy import signal
from scripts.received_voice_audit import stamp_counter,read_counter,audit_received_voice,receiver_origin,audit_device_deadlines


class ReceivedVoiceTests(unittest.TestCase):
    def test_device_deadlines_ignore_preroll_and_keep_tail_gate(self):
        rows=[{'event':'video_sent','frame_index':index,'due_ns':index*40_000_000,
               'camera_sent_ns':index*40_000_000+late*1_000_000}
              for index,late in enumerate([100]*8+[1]*99+[40])]
        self.assertTrue(audit_device_deadlines(rows)['passed'])
        rows[-1]['camera_sent_ns']+=1_000_000
        self.assertFalse(audit_device_deadlines(rows)['passed'])
        self.assertFalse(audit_device_deadlines(rows[:8])['passed'])

    def test_device_deadline_attribution_tracks_first_threshold_crossing(self):
        rows=[]
        for index,(taken,start,end) in enumerate([(6,7,8),(1,7,8),(-5,2,8),(1,2,3)],8):
            due=index*40_000_000
            rows.append({'event':'video_sent','frame_index':index,'due_ns':due,
                'video_dequeued_ns':due+taken*1_000_000,'camera_send_started_ns':due+start*1_000_000,
                'camera_sent_ns':due+end*1_000_000})
        result=audit_device_deadlines(rows)
        self.assertEqual(result['over_5ms_attributed'],{'before_dequeue':1,'before_send':1,'during_send':1})
        self.assertEqual(result['stages']['camera_send']['max_ms'],6)
        self.assertFalse(result['passed'])
        self.assertNotIn('callback_timing',result)
        for row in rows[:]:
            rows.append({'event':'audio_callback','frame_index':row['frame_index'],
                         'callback_ns':row['video_dequeued_ns']-500_000})
        callback_timing=audit_device_deadlines(rows)['callback_timing']
        self.assertEqual(callback_timing['over_5ms_at_callback'],1)
        self.assertEqual(callback_timing['callback_to_dequeue_p95_ms'],.5)

    def fixture(self,root,delay,wrong_voice=False,replace_frame=None,origin_ns=None,second_delay=None):
        source=np.random.default_rng(123).integers(-4000,4000,2400,dtype=np.int16)
        reference=root/'voice.wav'
        with wave.open(str(reference),'wb') as sound:
            sound.setparams((1,2,24000,0,'NONE','not compressed'));sound.writeframes(source.tobytes())
        audio=np.zeros(48000,dtype='<i2');offset=round((.24+delay)*48000)
        received_source=np.random.default_rng(999).integers(-4000,4000,2400,dtype=np.int16) if wrong_voice else source
        audio[offset:offset+4800]=signal.resample_poly(received_source.astype(float),2,1).astype('<i2')
        if second_delay is not None:
            second_source=np.random.default_rng(456).integers(-4000,4000,2400,dtype=np.int16)
            second_reference=root/'voice-2.wav'
            with wave.open(str(second_reference),'wb') as sound:
                sound.setparams((1,2,24000,0,'NONE','not compressed'));sound.writeframes(second_source.tobytes())
            offset=round((.64+second_delay)*48000)
            audio[offset:offset+4800]=signal.resample_poly(second_source.astype(float),2,1).astype('<i2')
        path=root/'capture.mkv'
        with av.open(str(path),'w') as output:
            video=output.add_stream('ffv1',rate=25);video.width=720;video.height=1280;video.pix_fmt='bgr0'
            sound=output.add_stream('pcm_s16le',rate=48000);sound.layout='mono'
            frame=av.AudioFrame.from_ndarray(audio.reshape(1,-1),format='s16',layout='mono')
            frame.sample_rate=48000;frame.pts=0;frame.time_base=Fraction(1,48000)
            output.mux(sound.encode(frame))
            image=np.zeros((1280,720,3),np.uint8)
            for index in range(25):
                marker=replace_frame[1] if replace_frame and index==replace_frame[0] else index
                frame=av.VideoFrame.from_ndarray(stamp_counter(image,marker),format='bgr24')
                frame.pts=index;frame.time_base=Fraction(1,25);output.mux(video.encode(frame))
            output.mux(video.encode(None));output.mux(sound.encode(None))
        events=[{'source_id':'idle-0','samples':5760},{'source_id':'speech','samples':2400}]
        source={'path':str(reference)}
        if origin_ns is not None:source['wav_ready_unix_ns']=origin_ns-100_000_000
        expected={'speech':source}
        if second_delay is not None:
            events.extend([{'source_id':'idle-1','samples':7200},{'source_id':'speech-2','samples':2400}])
            expected['speech-2']={'path':str(second_reference)}
        return audit_received_voice(path,events,expected,origin_ns)

    def test_receiver_origin_and_wav_ready_latency(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            log=root/'receiver.log'
            log.write_text('  Duration: N/A, start: 1700000000.123456, bitrate: N/A\n',encoding='utf-8')
            origin=1_700_000_000_123_456_000
            self.assertEqual(receiver_origin(log,origin-1,origin+1),origin)
            self.assertIsNone(receiver_origin(log,origin+1,origin+2))
            result=self.fixture(root,.02,origin_ns=origin)
        self.assertAlmostEqual(result['receiver_latency_calibration']['frame']['p95_ms'],340,delta=.1)
        self.assertAlmostEqual(result['receiver_latency_calibration']['signal']['p95_ms'],360,delta=1)

    def test_counter_wrap_and_input_ownership(self):
        image=np.zeros((1280,720,3),np.uint8)
        for index in [0,255,256,499,65535]:self.assertEqual(read_counter(stamp_counter(image,index)),index)
        self.assertFalse(image.any())
        with self.assertRaises(ValueError):stamp_counter(image,65536)

    def test_actual_decode_finds_voice_and_twenty_ms_offset(self):
        with tempfile.TemporaryDirectory() as temporary:result=self.fixture(Path(temporary),.02)
        self.assertTrue(result['voice_sync_passed']);self.assertTrue(result['frame_continuity_passed'])
        self.assertTrue(result['speech_frame_continuity_passed'])
        self.assertAlmostEqual(result['voices'][0]['av_offset_ms'],20,delta=.1)
        self.assertGreater(result['voices'][0]['correlation'],.99)

    def test_late_audio_and_wrong_voice_fail(self):
        for delay,wrong in [(.12,False),(.02,True)]:
            with self.subTest(delay=delay,wrong=wrong),tempfile.TemporaryDirectory() as temporary:
                self.assertFalse(self.fixture(Path(temporary),delay,wrong)['voice_sync_passed'])

    def test_late_matched_audio_still_measures_first_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            result=self.fixture(Path(temporary),.12,origin_ns=1_700_000_000_000_000_000)
        self.assertFalse(result['voice_sync_passed'])
        self.assertAlmostEqual(result['receiver_latency_calibration']['frame']['p95_ms'],340,delta=.1)
        self.assertAlmostEqual(result['receiver_latency_calibration']['signal']['p95_ms'],460,delta=1)

    def test_late_endpoints_still_measure_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            result=self.fixture(Path(temporary),.12,second_delay=.17)
        self.assertFalse(result['voice_sync_passed'])
        self.assertAlmostEqual(result['speech_av_drift_ms'],50,delta=.1)
        self.assertAlmostEqual(result['speech_measurement_span_seconds'],.4)

    def test_active_speech_drop_and_repeat_fail_even_when_in_sync(self):
        with tempfile.TemporaryDirectory() as temporary:
            result=self.fixture(Path(temporary),.02,replace_frame=(7,6))
        self.assertTrue(result['voice_sync_passed'])
        self.assertFalse(result['speech_frame_continuity_passed'])
        self.assertEqual((result['speech_missing_frames'],result['speech_repeated_frames']),(1,1))

    def test_idle_drop_does_not_count_as_speech_loss(self):
        with tempfile.TemporaryDirectory() as temporary:
            result=self.fixture(Path(temporary),.02,replace_frame=(2,1))
        self.assertFalse(result['frame_continuity_passed'])
        self.assertTrue(result['speech_frame_continuity_passed'])
        self.assertEqual(result['repeated_frame_indices'], {1: 1})
        self.assertEqual(result['missing_frame_ranges'], [[2, 2]])

    def test_nonadjacent_replay_is_counted_as_duplicate_and_reorder(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = self.fixture(Path(temporary), .02, replace_frame=(3, 1))
        self.assertEqual(result['repeated_frame_indices'], {1: 1})
        self.assertEqual(result['reordered_frames'], 1)
        self.assertEqual(result['missing_frame_ranges'], [[3, 3]])
