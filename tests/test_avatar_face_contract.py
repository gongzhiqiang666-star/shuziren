from pathlib import Path
import tempfile
import unittest
import cv2
import numpy as np

from recovered.image_clone_generate_data import _face_landmarks
from recovered.image_face_detect import FaceDetect, resolve_landmark_model_file


class FaceContractTests(unittest.TestCase):
    def test_reference_crop_context_two_passes_and_integer_offsets(self):
        class Detector:
            def get_bboxes(self, frame):
                return np.array([[20,10,60,50,.9]]), None
        class Landmarks:
            def forward(self, crop):
                self.crop = crop
                return np.full((1,68,2), .5)
        frame=np.arange(80*100*3,dtype=np.uint8).reshape(80,100,3)
        landmarks=Landmarks()
        points=_face_landmarks(frame,Detector(),landmarks)
        self.assertEqual(landmarks.crop.shape,(44,49,3))
        np.testing.assert_array_equal(landmarks.crop[0,0],frame[10,16])
        np.testing.assert_array_equal(points,np.tile([16,10],(68,1)))
        self.assertEqual(points.dtype,np.int32)
        _face_landmarks(frame,Detector(),landmarks,include_right=False)
        self.assertEqual(landmarks.crop.shape,(44,48,3))

    def test_bgr_array_and_file_use_identical_detector_colors(self):
        class Detector:
            def detect(self, image, **kwargs):
                self.image=image.copy()
                return np.empty((0,5)),None
        model=FaceDetect.__new__(FaceDetect);model.det_model=Detector()
        image=np.full((4,4,3),[10,30,90],dtype=np.uint8)
        model.get_bboxes(image)
        np.testing.assert_array_equal(model.det_model.image[0,0],[90,30,10])
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'frame.png';cv2.imwrite(str(path),image)
            model.get_bboxes(path)
            np.testing.assert_array_equal(model.det_model.image[0,0],[90,30,10])

    def test_actual_landmark_filename_resolution(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'nested/pfpld_robust_sim_bs1_8003.onnx'
            path.parent.mkdir();path.touch()
            self.assertEqual(resolve_landmark_model_file(directory),path)


if __name__=='__main__':
    unittest.main()
