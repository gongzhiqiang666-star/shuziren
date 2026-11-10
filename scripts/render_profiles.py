"""Explicit per-job profiles; selecting one never silently selects another."""
PROFILES={
    'standard':{'backend':'cuda','encoder':'legacy','strict_precision':False},
    'trt-nvenc':{'backend':'tensorrt','encoder':'h264_nvenc','strict_precision':True},
}


def result_matches(name,result,allow_legacy=False):
    if name not in PROFILES:return False
    if allow_legacy and name=='standard' and 'render_profile' not in result:return True
    expected=PROFILES[name]
    return result.get('render_profile')==name and result.get('backend')==expected['backend'] and result.get('video_encoder')==expected['encoder']
