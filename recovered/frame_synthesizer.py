"""Recovered image preprocessing for the v2 frame synthesis model."""

import numpy as np


def resize_face_crop(image: np.ndarray, bounding_box, img_size: int) -> np.ndarray:
    """Crop using the stored axis pairs and resize to the padded model size."""
    import cv2

    left, right, top, bottom = map(int, bounding_box)
    side = img_size + int(img_size / 256) * 10
    return cv2.resize(
        image[top:bottom, left:right], (side, side), interpolation=cv2.INTER_CUBIC
    )


def tensor_norm_no_training(img_tensor, mask=None):
    """Scale pixel values to [0, 1] and apply the optional inference mask."""
    normalized = img_tensor / 255.0
    if mask is not None:
        normalized = normalized * mask
    return normalized


def transpose_audio_window(window: np.ndarray) -> np.ndarray:
    """Convert a (20, 256) WeNet window to (256, 20) for synthesis."""
    return window.transpose()


def get_batch_audio_features(windows: list[np.ndarray]) -> list[np.ndarray]:
    """Prepare each window for synthesis, preserving the batch order."""
    return [
        transpose_audio_window(window)
        if window.shape[0] == 20 and window.shape[1] == 256
        else window
        for window in windows
    ]


def run_synthesis_model(
    session, source_img: np.ndarray, ref_img: np.ndarray, audio_feature: np.ndarray
) -> np.ndarray:
    """Run the packaged v2 ONNX graph with preprocessed float32 inputs."""
    return session.run(
        ["output"],
        {
            "source_img": source_img,
            "ref_img": ref_img,
            "audio_feature": audio_feature,
        },
    )[0]


def crop_synthesis_interior(image: np.ndarray, img_size: int) -> np.ndarray:
    """Apply the v2 process_batch border slices to an HWC image."""
    margin = int((img_size / 256) * 5)
    return image[margin:-margin, margin:-margin]


def paste_synthesis_interior(
    image: np.ndarray, synthesized: np.ndarray, img_size: int
) -> np.ndarray:
    """Replace the interior of a copy of the padded face crop."""
    result = image.copy()
    crop_synthesis_interior(result, img_size)[...] = synthesized
    return result


def paste_fused_crop_rectangle(
    image: np.ndarray,
    fused_crop: np.ndarray,
    bounding_box,
    *,
    inplace: bool = False,
) -> np.ndarray:
    """Resize a fused face to its stored rectangle and paste it into the frame."""
    import cv2

    left, right, top, bottom = map(int, bounding_box)
    target_width = right - left
    target_height = bottom - top
    if fused_crop.shape[:2] != (target_height, target_width):
        fused_crop = cv2.resize(
            fused_crop,
            (target_width, target_height),
            interpolation=cv2.INTER_LINEAR,
        )

    result = image if inplace else image.copy()
    result[top:bottom, left:right] = fused_crop
    return result
