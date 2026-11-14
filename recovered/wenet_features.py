"""Device-safe WeNet feature extraction around authorized provider modules."""

import numpy as np


def model_device(model):
    import torch
    try:
        return next(model.parameters()).device
    except StopIteration:
        return torch.device('cpu')


def compute_bnf(provider, wav_path, model, section=560000):
    """Run provider preprocessing while keeping tensors on the model device."""
    import torch
    if type(section) is not int or section <= 0:
        raise ValueError('section must be a positive integer')
    device = model_device(model)
    params = provider.hparams1
    waveform = provider.load_wav(str(wav_path), sr=params['sample_rate'])
    waveform = np.concatenate((np.zeros(6400), waveform, np.zeros(6400)))
    results = []
    # Preserve the provider's historical ``len // section + 1`` behavior,
    # including its padded tail block when the length is an exact multiple.
    for index in range(len(waveform) // section + 1):
        start = index * section
        block = waveform[start:min(start + section, len(waveform))]
        padded = len(block) < params['sample_rate']
        if padded:
            block = np.append(block, np.zeros(params['sample_rate']))
        mel, _ = provider.wav2mfcc_v2(
            block, sr=params['sample_rate'], n_mfcc=params['n_mfcc'],
            n_fft=params['n_fft'], hop_len=params['hop_length'],
            win_len=params['win_length'], window=params['window'],
            num_mels=params['num_mels'], center=params['center'],
        )
        inputs = torch.from_numpy(mel).float().to(device).unsqueeze(0)
        lengths = torch.tensor([mel.shape[0]], dtype=torch.long, device=device)
        with torch.no_grad():
            value = model(inputs, lengths).squeeze(0).cpu().numpy()
        if padded and value.shape[0] > 25:
            value = value[:-25]
        results.append(value)
    if not results:
        raise ValueError('WeNet provider produced no feature blocks')
    return np.concatenate(results, axis=0)
