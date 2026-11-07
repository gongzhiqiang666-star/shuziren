"""Recovered RapidOCR adapter for automatic live controls."""

from __future__ import annotations


class OCRProcessor:
    def __init__(self):
        try:
            from rapidocr import RapidOCR
        except ImportError as error:
            raise RuntimeError("自动直播动作需要 rapidocr") from error
        self.ocr = RapidOCR()

    def recognize_text(self, image):
        if image is None:
            return []
        result = self.ocr(image)
        output = []

        if all(hasattr(result, name) for name in ("boxes", "txts", "scores")):
            if not result.boxes:
                return []
            data_list = zip(result.boxes, result.txts, result.scores)
            for box, text, score in data_list:
                output.append({"box": box, "text": text, "score": score})
            return output

        if not result:
            return []
        data_list = result
        if (isinstance(result, (list, tuple)) and len(result) > 0
                and isinstance(result[0], (list, tuple)) and len(result[0]) > 0
                and isinstance(result[0][0], (list, tuple))
                and len(result) == 2
                and not isinstance(result[1], (list, tuple, dict))):
            data_list = result[0]
        for item in data_list:
            if isinstance(item, (list, tuple)) and len(item) > 1:
                output.append({
                    "box": item[0],
                    "text": item[1],
                    "score": item[2] if len(item) >= 3 else None,
                })
        return output
