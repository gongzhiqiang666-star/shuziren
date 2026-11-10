"""Frozen corpus normalization and encoded-video precision comparison."""
from ast import literal_eval
import json
from pathlib import Path
import re
import unicodedata


def normalize(text,item):
    text=unicodedata.normalize('NFKC',text).lower()
    pairs=[(alias.lower(),group[0].lower()) for group in item.get('equivalences',[]) for alias in group]
    for alias,target in sorted(pairs,key=lambda pair:len(pair[0]),reverse=True):
        pattern=re.escape(alias)
        if alias[0].isdigit():pattern=r'(?<![0-9.])'+pattern
        if alias[-1].isdigit():pattern+=r'(?![0-9.])'
        text=re.sub(pattern,lambda match:target,text)
    return re.sub(r'[^\w]','',text)


def content_score(actual,item,maximum):
    from scripts.validate_tts_quality import character_error_rate
    actual=normalize(actual,item);expected=normalize(item['expected'],item)
    cer=character_error_rate(expected,actual)
    missing=[token for token in item.get('required_tokens',[]) if normalize(token,item) not in actual]
    return {'normalized_actual':actual,'normalized_expected':expected,'cer':cer,
            'missing_required_tokens':missing,'passed':cer<=maximum and not missing}


def compare_videos(left,right,avatar_directory,thresholds):
    import cv2
    import numpy as np
    avatar=Path(avatar_directory);count=len(list((avatar/'frames').glob('*.jpg')))
    captures=[cv2.VideoCapture(str(path)) for path in (left,right)]
    maes=[];whole=[];index=0;metadata_cache={}
    try:
        while True:
            ok,a=captures[0].read();other,b=captures[1].read()
            if ok!=other:raise ValueError('两个后端输出帧数不同')
            if not ok:break
            if a.shape!=b.shape:raise ValueError('两个后端输出尺寸不同')
            delta=np.abs(a.astype(np.float32)-b.astype(np.float32));whole.append(float(delta.mean()))
            period=max(1,2*count-2);source=index%period
            if source>=count:source=period-source
            if source not in metadata_cache:
                values={}
                for line in (avatar/'positions'/f'{source:06d}.txt').read_text(encoding='utf-8').splitlines():
                    key,sep,value=line.partition(':')
                    if sep:values[key.strip()]=literal_eval(value.strip())
                metadata_cache[source]=values
            points=np.asarray(metadata_cache[source].get('landmarks',[]))
            if points.shape==(68,2):
                mouth=points[48:68]
                x0,y0=np.floor(mouth.min(axis=0)-12).astype(int);x1,y1=np.ceil(mouth.max(axis=0)+12).astype(int)
                x0=max(0,x0);y0=max(0,y0);x1=min(a.shape[1],x1);y1=min(a.shape[0],y1)
                if x1>x0 and y1>y0:maes.append(float(delta[y0:y1,x0:x1].mean()))
            index+=1
    finally:
        for capture in captures:capture.release()
    mean=float(np.mean(maes)) if maes else None;p95=float(np.percentile(maes,95)) if maes else None
    coverage=len(maes)/index if index else 0
    return {'frames':index,'mouth_roi_coverage':coverage,'mouth_mae_mean':mean,'mouth_mae_p95':p95,
            'whole_frame_mae_mean':float(np.mean(whole)) if whole else None,
            'passed':bool(index and coverage>=thresholds['roi_coverage_min'] and mean is not None
                and mean<=thresholds['fp16_roi_mae_mean_max'] and p95<=thresholds['fp16_roi_mae_p95_max'])}
