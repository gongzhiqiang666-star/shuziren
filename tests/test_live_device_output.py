import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
import numpy as np
from scripts.live_device_output import VirtualAudioOutput,VirtualCameraOutput


class DeviceOutputTests(unittest.TestCase):
    def test_camera_enforces_order_shape_and_stop(self):
        camera=Mock();module=SimpleNamespace(Camera=Mock(return_value=camera),PixelFormat=SimpleNamespace(BGR='BGR'))
        with patch.dict(sys.modules,{'pyvirtualcam':module}):
            output=VirtualCameraOutput(24,32);image=np.zeros((32,24,3),np.uint8)
            for index,frame in [(1,image),(0,image[:1])]:
                with self.assertRaises(ValueError):output.send(index,frame)
            output.send(0,image);camera.send.assert_called_once()
            output.close();output.close();camera.close.assert_called_once()
            with self.assertRaises(RuntimeError):output.send(1,image)

    def test_audio_has_explicit_device_conversion_and_reports_underflow(self):
        stream=Mock();stream.write.return_value=True
        module=Mock();module.query_devices.return_value={'max_output_channels':2,'hostapi':2}
        module.query_hostapis.return_value={'name':'Windows WASAPI'};module.RawOutputStream.return_value=stream
        with patch.dict(sys.modules,{'sounddevice':module}):
            with self.assertRaises(ValueError):VirtualAudioOutput(None)
            output=VirtualAudioOutput(14)
            module.WasapiSettings.assert_called_once_with(auto_convert=True)
            self.assertTrue(output.write(bytes(1920)));self.assertEqual((output.samples,output.underflows),(960,1))
            output.close(abort=True);output.close();stream.abort.assert_called_once();stream.close.assert_called_once()
            with self.assertRaises(RuntimeError):output.write(bytes(1920))

    def test_audio_start_failure_closes_and_does_not_fallback(self):
        module=Mock();module.query_devices.return_value={'max_output_channels':2,'hostapi':2}
        module.query_hostapis.return_value={'name':'Windows WASAPI'}
        module.RawOutputStream.return_value.start.side_effect=RuntimeError('device busy')
        with patch.dict(sys.modules,{'sounddevice':module}):
            with self.assertRaisesRegex(RuntimeError,'device busy'):VirtualAudioOutput(14)
            module.RawOutputStream.assert_called_once();module.RawOutputStream.return_value.close.assert_called_once()
