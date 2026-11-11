"""Sample DirectShow packet timestamps alongside the receiver's system clock."""
import argparse
import json
import time
from pathlib import Path

import av
from scripts.received_voice_audit import read_counter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', required=True, help='DirectShow input specifier')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--packets', type=int, default=300)
    parser.add_argument('--read-frame-counters', action='store_true',
                        help='Decode the frame numbers stamped on diagnostic video')
    args = parser.parse_args()
    if args.packets < 1:
        parser.error('--packets must be positive')

    options = {'use_video_device_timestamps': '0', 'video_size': '720x1280',
               'framerate': '25', 'rtbufsize': '16000000', 'audio_buffer_size': '20'}
    samples = []
    with av.open(args.device, format='dshow', options=options, timeout=(5, 5)) as capture:
        for packet in capture.demux():
            received_ns = time.perf_counter_ns()
            received_unix_ns = time.time_ns()
            if packet.pts is None or packet.time_base is None:
                continue
            sample = {'stream': packet.stream.index, 'type': packet.stream.type,
                      'pts': packet.pts, 'time_base': str(packet.time_base),
                      'received_ns': received_ns, 'received_unix_ns': received_unix_ns}
            if args.read_frame_counters and packet.stream.type == 'video':
                sample['frame_counters'] = [read_counter(frame.to_ndarray(format='bgr24'))
                                            for frame in packet.decode()]
            samples.append(sample)
            if len(samples) == args.packets:
                break
    args.output.write_text(json.dumps(samples, indent=2), encoding='utf-8')
    if len(samples) != args.packets:
        raise RuntimeError(f'Expected {args.packets} timestamped packets, received {len(samples)}')


if __name__ == '__main__':
    main()
