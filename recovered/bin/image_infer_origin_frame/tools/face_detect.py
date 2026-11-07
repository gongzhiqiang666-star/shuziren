from recovered.image_face_detect import *
from recovered.image_face_detect import pfpld as _pfpld


class pfpld(_pfpld):
    def forward(self, image):
        return super().forward(image)
