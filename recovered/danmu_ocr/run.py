import argparse
from . import ocr_capture

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", default="general")
    args = parser.parse_args()
    try:
        ocr_capture.start_window(platform=args.platform)
    except TypeError:
        ocr_capture.start_window()
