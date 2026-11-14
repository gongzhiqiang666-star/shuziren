"""Send a moving KT product overlay through the virtual camera and capture it via DirectShow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import time

import av
import cv2
import numpy as np

from recovered.product_kt_overlay import ProductKtOverlay
from scripts.live_device_output import VirtualCameraOutput


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ffmpeg', required=True, type=Path)
    parser.add_argument('--report-dir', required=True, type=Path)
    parser.add_argument('--camera-input', default='Tblive Virtual Camera')
    args = parser.parse_args(argv)
    if not args.ffmpeg.is_file():
        raise SystemExit('packaged FFmpeg is missing')
    report_dir = args.report_dir.resolve(); report_dir.mkdir(parents=True, exist_ok=False)
    receiver = report_dir / 'kt-device-receiver.mkv'
    log_path = report_dir / 'receiver.log'

    width, height, send_fps, capture_fps, send_frames = 1280, 720, 25, 30, 175
    with tempfile.TemporaryDirectory(prefix='kt-device-') as raw:
        root = Path(raw)
        product_path = root / 'product.png'
        product = np.zeros((180, 260, 4), np.uint8)
        product[..., 1] = 245
        product[..., 3] = 220
        cv2.rectangle(product, (15, 15), (244, 164), (20, 180, 20, 255), 8)
        cv2.imwrite(str(product_path), product)

        overlay = ProductKtOverlay()
        quads = []
        for index in range(send_frames):
            x = 120 + round(560 * index / (send_frames - 1))
            y = 185 + round(55 * np.sin(index / 18))
            quads.append(np.float32([[x, y], [x + 350, y + 10],
                                     [x + 330, y + 300], [x - 20, y + 285]]))
        overlay._boxes = quads
        overlay._precomputed = overlay._boxes
        overlay._frame_size = (width, height)
        overlay.set_product_image(goods_id=1, item_pic=str(product_path), item_name='设备回采商品')
        overlay.set_enabled(True)

        with log_path.open('wb') as log:
            capture = subprocess.Popen([
                str(args.ffmpeg), '-nostdin', '-y', '-hide_banner', '-loglevel', 'info', '-nostats',
                '-use_wallclock_as_timestamps', '1', '-f', 'dshow', '-rtbufsize', '64M',
                '-video_size', f'{width}x{height}', '-framerate', str(capture_fps),
                '-i', 'video=' + args.camera_input, '-t', '5.5', '-fps_mode', 'cfr',
                '-c:v', 'ffv1', str(receiver),
            ], stdout=subprocess.DEVNULL, stderr=log)
            camera = None
            try:
                time.sleep(0.8)
                camera = VirtualCameraOutput(width, height, backend='obs', pixel_format='BGR')
                start = time.perf_counter()
                for index in range(send_frames):
                    frame = np.full((height, width, 3), (38, 32, 28), np.uint8)
                    cv2.putText(frame, f'KT {index:03d}', (30, 80), cv2.FONT_HERSHEY_SIMPLEX,
                                1.5, (220, 220, 220), 3, cv2.LINE_AA)
                    camera.send(index, overlay.apply(frame, physical_index=index))
                    due = start + (index + 1) / send_fps
                    delay = due - time.perf_counter()
                    if delay > 0:
                        time.sleep(delay)
                capture.wait(timeout=12)
                if capture.returncode:
                    raise RuntimeError('DirectShow capture failed; see receiver.log')
            finally:
                if camera is not None:
                    camera.close()
                if capture.poll() is None:
                    capture.kill(); capture.wait(timeout=5)

    frames = []
    centroids = []
    with av.open(str(receiver)) as container:
        for frame in container.decode(video=0):
            image = frame.to_ndarray(format='bgr24')
            hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(hsv, (35, 80, 80), (90, 255, 255))
            count = int(cv2.countNonZero(mask))
            frames.append(count)
            moments = cv2.moments(mask)
            if moments['m00']:
                centroids.append((moments['m10'] / moments['m00'], moments['m01'] / moments['m00']))
    visible = [count for count in frames if count > 10_000]
    if len(frames) < 100 or len(visible) < int(len(frames) * 0.8) or len(centroids) < 2:
        raise RuntimeError(f'captured KT product is incomplete: frames={len(frames)} visible={len(visible)}')
    movement = max(point[0] for point in centroids) - min(point[0] for point in centroids)
    if movement < 100:
        raise RuntimeError(f'captured KT product did not move enough: {movement:.3f}px')
    decode = subprocess.run([str(args.ffmpeg), '-v', 'error', '-xerror', '-i', str(receiver),
                             '-map', '0:v:0', '-f', 'null', '-'], capture_output=True, timeout=30)
    if decode.returncode:
        raise RuntimeError('full receiver decode failed')
    report = {
        'passed': True, 'camera_input': args.camera_input,
        'camera_output': camera.device, 'sent_frames': send_frames,
        'captured_frames': len(frames), 'visible_product_frames': len(visible),
        'green_centroid_x_movement_px': movement,
        'full_decode_exit_code': decode.returncode,
        'receiver': str(receiver), 'scope': 'dynamic KT overlay through virtual camera and DirectShow; no subjective edge-quality claim',
    }
    (report_dir / 'result.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
