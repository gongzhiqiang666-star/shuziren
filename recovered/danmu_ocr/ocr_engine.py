"""RapidOCR adapter for the recovered capture process."""


class OCRProcessor:
    def __init__(self):
        from rapidocr import RapidOCR
        self.ocr_processor = RapidOCR()

    @classmethod
    def _from_engine(cls, engine):
        instance = cls.__new__(cls); instance.ocr_processor = engine; return instance

    def recognize_text(self, image):
        result = self.ocr_processor(image)
        if not result or not result.txts:
            return []
        if result.boxes is None:
            return []

        lines = [
            (box[0][1], text)
            for box, text, _score in zip(result.boxes, result.txts, result.scores)
        ]
        return [text for _, text in sorted(lines, key=lambda line: line[0])]
