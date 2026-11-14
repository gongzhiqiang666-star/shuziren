"""Aspect-safe frame placement shared by fixed-size live outputs."""


def fit_frame_to_canvas(frame, width, height):
    """Scale to cover and center-crop without stretching the source aspect."""
    import cv2

    target_width, target_height = int(width), int(height)
    if target_width <= 0 or target_height <= 0:
        raise ValueError("输出画布尺寸必须为正数")
    source_height, source_width = frame.shape[:2]
    if source_width <= 0 or source_height <= 0:
        raise ValueError("输入画面尺寸必须为正数")
    if (source_width, source_height) == (target_width, target_height):
        return frame

    scale = max(target_width / source_width, target_height / source_height)
    scaled_width = max(target_width, int(round(source_width * scale)))
    scaled_height = max(target_height, int(round(source_height * scale)))
    interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
    resized = cv2.resize(frame, (scaled_width, scaled_height), interpolation=interpolation)
    left = (scaled_width - target_width) // 2
    top = (scaled_height - target_height) // 2
    return resized[top:top + target_height, left:left + target_width]
