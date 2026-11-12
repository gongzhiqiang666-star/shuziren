"""Receiver marker analysis; retain loss and onset uncertainty separately."""
MARKERS=(25,65,105)
FLASH_FRAMES=3


def is_flash(index):
    return any(start<=index<start+FLASH_FRAMES for start in MARKERS)


def analyze_markers(video,audio_times):
    """video entries: (source frame index, common-clock seconds, flash seen)."""
    starts=[];previous=False
    for index,stamp,flash in video:
        if flash and not previous:starts.append((index,stamp))
        previous=flash
    steps=[b[0]-a[0] for a,b in zip(video,video[1:])]
    indices = {frame[0] for frame in video}
    result={'visual_events':starts,'audio_marker_times':audio_times,
        'repeated_frames':len(video) - len(indices),
        'missing_frames':max(indices) - min(indices) + 1 - len(indices) if indices else 0,
        'reordered_frames':sum(step<0 for step in steps),
        'frame_continuity_passed':bool(steps) and all(step==1 for step in steps),
        'av_offset_ms':[],'onset_uncertainty_ms':[],'receiver_sync_passed':False}
    if len(starts)!=len(MARKERS) or len(audio_times)!=len(MARKERS):
        result['sync_error']='Three matching audio and visual events required';return result
    for expected,(actual,stamp),audio in zip(MARKERS,starts,audio_times):
        if not expected<=actual<expected+FLASH_FRAMES:
            result['sync_error']='Visual marker identity/order mismatch';return result
        result['av_offset_ms'].append((audio-stamp)*1000)
        result['onset_uncertainty_ms'].append((actual-expected)*40)
    result['receiver_sync_passed']=not result['reordered_frames'] and all(
        abs(offset)+uncertainty<=80 for offset,uncertainty in zip(result['av_offset_ms'],result['onset_uncertainty_ms']))
    return result
