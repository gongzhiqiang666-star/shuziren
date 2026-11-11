"""Build an offline review sheet from measured results, leaving human fields pending."""
import argparse
import html
import json
import re
from pathlib import Path

from scripts.avatar_store import digest


def build(root):
    root=Path(root).resolve(strict=True)
    corpus=json.loads((root/'corpus.json').read_text(encoding='utf-8'))
    result=json.loads((root/'result.json').read_text(encoding='utf-8')) if (root/'result.json').exists() else None
    secondary=json.loads((root/'secondary-asr.json').read_text(encoding='utf-8')) if (root/'secondary-asr.json').exists() else {'cases':[]}
    extra={item['id']:item for item in secondary['cases']}
    escape=lambda value:html.escape(str(value),quote=True)
    cards=[]
    for item in corpus['items']:
        if not re.fullmatch(r'Q[0-9]{3}',item['id']):raise ValueError('复核项目编号无效')
        asr_path=root/'asr'/(item['id']+'.json')
        asr=json.loads(asr_path.read_text(encoding='utf-8')) if asr_path.exists() else None
        tts_path=root/'tts'/(item['id']+'.json')
        audio=json.loads(tts_path.read_text(encoding='utf-8'))['result'] if tts_path.exists() else None
        source=''
        if audio:
            path=Path(audio['output']).resolve();path.relative_to(root)
            source=f'<audio controls preload="none" src="{escape(path.relative_to(root).as_posix())}"></audio>'
        status='未执行' if asr is None else '自动内容通过' if asr['passed'] else '自动内容待核对'
        players=''.join(f'<div><b>{label}</b><video controls preload="none" src="{backend}/{item["id"]}.mp4"></video></div>'
                        for backend,label in [('cuda','CUDA FP32'),('tensorrt','TensorRT FP16')])
        texts=''
        if asr:texts=f'<p>本地ASR：{escape(asr["transcript"])}；CER {asr["cer"]:.3f}；缺失关键项：{escape(asr["missing_required_tokens"])}</p>'
        if item['id'] in extra:
            texts+=''.join(f'<p>Whisper {escape(kind)}：{escape(value["transcript"])}</p>' for kind,value in extra[item['id']]['secondary'].items())
        cards.append(f'''<section data-case="{item['id']}"><h2>{item['id']} · {escape(item['category'])} · {status}</h2>
<p>文本：{escape(item['text'])}；语速 {item['speed']}</p>{texts}{source}<div class="players">{players}</div>
<label>听感/嘴周/身份/末句人工检查：<select><option value="pending">待检查</option><option value="pass">通过</option><option value="fail">失败</option></select></label>
<label>具体问题与复查说明：<textarea rows="2"></textarea></label></section>''')
    metadata={'protocol':corpus['version'],'corpus_sha256':digest(root/'corpus.json'),'run_directory':str(root)}
    script='''const metadata=METADATA;
const cards=[...document.querySelectorAll('[data-case]')];
const draftKey='v04-review:'+metadata.run_directory+':'+metadata.corpus_sha256;
const readCases=()=>cards.map(el=>({id:el.dataset.case,status:el.querySelector('select').value,notes:el.querySelector('textarea').value}));
try {
const draft=new Map(JSON.parse(localStorage.getItem(draftKey)||'[]').map(item=>[item.id,item]));
cards.forEach(el=>{
const item=draft.get(el.dataset.case);
if(!item)return;
el.querySelector('select').value=item.status;
el.querySelector('textarea').value=item.notes;
});
} catch {
document.querySelector('#draft-status').textContent='无法读取本地草稿，可手动导出记录。';
}
document.addEventListener('input',event=>{
if(!event.target.closest('[data-case]'))return;
try {
localStorage.setItem(draftKey,JSON.stringify(readCases()));
document.querySelector('#draft-status').textContent='已保存到本机浏览器';
} catch {
document.querySelector('#draft-status').textContent='本地草稿无法保存，请导出记录。';
}
});
document.querySelectorAll('audio,video').forEach(media=>media.addEventListener('play',()=>{
document.querySelectorAll('audio,video').forEach(other=>{if(other!==media) other.pause();});
}));
document.querySelector('#export').addEventListener('click',()=>{
const cases=readCases();
const content={...metadata,exported_at:new Date().toISOString(),cases};const url=URL.createObjectURL(new Blob([JSON.stringify(content,null,2)],{type:'application/json'}));
const link=document.createElement('a');link.href=url;link.download='quality-manual-review.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});'''.replace('METADATA',json.dumps(metadata,ensure_ascii=False).replace('<','\\u003c'))
    summary='尚未完成自动汇总' if result is None else json.dumps({key:result[key] for key in ['acceptance_status','content_failures','precision_failures','backend_capacity']},ensure_ascii=False,indent=2)
    page=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>V04质量复核</title>
<style>body{{font:16px system-ui;max-width:1100px;margin:auto;padding:24px;background:#f3f5f9;color:#17243b}}section{{background:white;padding:24px;margin:20px 0;border-radius:12px}}.players{{display:flex;gap:20px;flex-wrap:wrap}}video{{display:block;width:300px;max-width:100%}}label{{display:block;margin-top:16px}}textarea{{width:95%}}pre{{white-space:pre-wrap}}</style>
<h1>{escape(corpus['version'])} 质量复核记录</h1><p>自动结果不代替人工听感和动态画质。以下人工字段初始全部待检查；本页不自动上传、播放或开播。</p>
<button id="export">导出当前人工检查记录</button> <span id="draft-status" role="status"></span><pre>{escape(summary)}</pre>{''.join(cards)}<script>{script}</script></html>'''
    (root/'review.html').write_text(page,encoding='utf-8')
    return root/'review.html'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run-directory',required=True,type=Path)
    print(build(parser.parse_args().run_directory))


if __name__=='__main__':main()
