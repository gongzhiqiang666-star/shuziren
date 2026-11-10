"""Offline objective checks for an A/B/A synthesis report, not human listening."""
import argparse
import json
import os
from pathlib import Path
import re


def character_error_rate(expected, actual):
    normalize = lambda value: re.sub(r'[^\w]', '', value).lower()
    expected, actual = normalize(expected), normalize(actual)
    row = list(range(len(actual) + 1))
    for i, left in enumerate(expected, 1):
        next_row = [i]
        for j, right in enumerate(actual, 1):
            next_row.append(min(next_row[-1] + 1, row[j] + 1, row[j-1] + (left != right)))
        row = next_row
    return row[-1] / max(1, len(expected))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime-root', required=True, type=Path)
    parser.add_argument('--switch-report', required=True, type=Path)
    parser.add_argument('--speaker-model', required=True, type=Path)
    args = parser.parse_args()
    os.environ['PATH'] = str(args.runtime_root/'_internal/env/ffmpeg/bin') + os.pathsep + os.environ.get('PATH', '')
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['MODELSCOPE_OFFLINE'] = '1'
    root = args.switch_report.resolve().parent
    report = {'status': 'failed', 'listening_verified': False,
              'thresholds': {'max_cer': .15, 'min_reference_margin': .05}, 'samples': []}
    try:
        import torch
        import torchaudio
        from funasr.models.campplus.model import CAMPPlus
        from funasr.models.campplus.utils import extract_feature
        from recovered.funasr_runtime import load_funasr_model, transcribe_with_funasr, funasr_result_to_text
        from scripts.voice_store import VoiceStore
        source = json.loads(args.switch_report.read_text(encoding='utf-8'))
        assert source['status'] == 'passed' and len(source['outputs']) == 3
        store = VoiceStore(root)
        references = [store.audio_path(item['voice_id']) for item in source['outputs'][:2]]
        config = json.loads((args.speaker_model/'configuration.json').read_text(encoding='utf-8'))['model']
        model = CAMPPlus(feat_dim=config['model_config']['fbank_dim'],
                         embedding_size=config['model_config']['emb_size']).eval()
        model.load_state_dict(torch.load(args.speaker_model/config['pretrained_model'],
                                        map_location='cpu', weights_only=True), strict=True)
        torch.set_num_threads(4)
        def embedding(path):
            audio, rate = torchaudio.load(str(path))
            audio = torchaudio.functional.resample(audio.mean(dim=0), rate, 16000)
            features, _, _ = extract_feature([audio])
            with torch.inference_mode():
                return model(features).reshape(1, -1)
        refs = [embedding(path) for path in references]
        cosine = lambda a, b: float(torch.nn.functional.cosine_similarity(a, b).item())
        report['reference_cosine'] = cosine(*refs)
        # A margin only has meaning when the two references are separable.
        report['references_separable'] = report['reference_cosine'] < .8
        for index, item in enumerate(source['outputs']):
            vector = embedding(item['output'])
            scores = [cosine(vector, ref) for ref in refs]
            intended = index % 2
            report['samples'].append({'output': item['output'], 'reference_scores': scores,
                'intended_reference': intended, 'reference_margin': scores[intended]-scores[1-intended]})
        del model
        asr = load_funasr_model(str(args.runtime_root/'_internal/assets/pretrained_models/asr'), prefer_fallback=True)
        for sample in report['samples']:
            text = funasr_result_to_text(transcribe_with_funasr(asr, sample['output'], sentence_timestamp=False))
            sample.update(transcript=text, cer=character_error_rate('这是主播的声音测试，请确认这段话清晰完整。', text))
        report['content_passed'] = all(item['cer'] <= .15 for item in report['samples'])
        report['reference_match_passed'] = report['references_separable'] and all(
            item['reference_margin'] >= .05 for item in report['samples'])
        report['status'] = 'passed' if report['content_passed'] and report['reference_match_passed'] else 'failed'
    except Exception as error:
        report['error'] = str(error)
    path = root/'quality-result.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': report['status'], 'report': str(path), 'error': report.get('error')}, ensure_ascii=False))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
