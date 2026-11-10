"""Check the exact owned bytes decoded for each model input frame."""
from ast import literal_eval
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

from scripts.avatar_store import AvatarError


class VerifiedAvatarReader:
    def __init__(self, directory, total_frames):
        self.root = Path(directory).resolve(strict=True)
        self.total_frames = total_frames
        self.hashes = json.loads((self.root/'manifest.json').read_text(encoding='utf-8'))['files']

    def _read(self, relative):
        path = (self.root/relative).resolve(strict=True)
        path.relative_to(self.root)
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != self.hashes.get(relative):
            raise AvatarError('形象素材已变化，请重新导入')
        return payload

    def load(self, frame_idx):
        index = int(frame_idx) % max(self.total_frames, 1)
        image = self._read(f'frames/{index:06d}.jpg')
        frame = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise AvatarError('形象帧无法解码')
        metadata = {}
        for line in self._read(f'positions/{index:06d}.txt').decode('utf-8').splitlines():
            key, sep, value = line.partition(':')
            if not sep:
                continue
            key, value = key.strip(), value.strip()
            if key in {'bounding_box', 'bbox', 'landmarks', 'positions', 'lmk'}:
                metadata[key] = np.asarray(literal_eval(value))
            elif key == 'is_no_face':
                metadata[key] = value.lower() == 'true'
        if 'bounding_box' not in metadata:
            metadata['is_no_face'] = True
        return frame, metadata
