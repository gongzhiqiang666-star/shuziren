"""Real GPU speech-to-avatar task lifecycle; not visual/listening acceptance."""
import argparse
import json
from pathlib import Path
import uuid

from scripts.avatar_store import AvatarStore
from scripts.product_store import ProductStore,Conflict
from scripts.render_tasks import RenderTasks
from scripts.tts_tasks import TTSTasks
from scripts.voice_store import VoiceStore


def wait(manager,timeout):
    monitor = manager.monitor
    if monitor is None:
        raise RuntimeError('尚未启动验证任务')
    monitor.join(timeout=timeout)
    if monitor.is_alive():
        raise TimeoutError('任务未在限定时间内结束')
    state = manager.state()
    if not state or state['status']=='running':
        raise RuntimeError('验证任务结束后缺少最终状态')
    return state


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--runtime-root',required=True,type=Path)
    parser.add_argument('--source-voice-data',required=True,type=Path)
    parser.add_argument('--source-avatar-directory',required=True,type=Path)
    parser.add_argument('--report-directory',required=True,type=Path)
    parser.add_argument('--render-profile',choices=['standard','trt-nvenc'],default='standard')
    args=parser.parse_args()
    root=(args.report_directory/('run-'+uuid.uuid4().hex)).resolve();root.mkdir(parents=True)
    report={'status':'failed','checks':{},'render_profile':args.render_profile,'visual_quality_verified':False};tts=renders=None
    try:
        source=VoiceStore(args.source_voice_data);reference=source.get(source.selected());voices=VoiceStore(root)
        voice=voices.import_audio(source.audio_path(reference['id']),reference['transcript'],'真实合成验证音色',
                                  args.runtime_root/'_internal/env/ffmpeg/bin/ffmpeg.exe')
        voices.select(voice['id']);avatars=AvatarStore(root)
        first_avatar=avatars.import_prepared(args.source_avatar_directory.resolve(),'合成验证形象')
        second_avatar=avatars.import_prepared(args.source_avatar_directory.resolve(),'切换失效验证形象')
        avatars.select(first_avatar['id'])
        products=ProductStore(root);product=products.save(title='视频闭环验证商品',content='仅限本机验证，不开播',product_index=9)
        products.select(product['id'])
        script=products.add_script(product,'现在验证数字人视频，语音和形象都来自当前选择。');products.select_script(product['id'],script)
        tts=TTSTasks(args.runtime_root,root);tts.start(product['id'],script,voice['id'])
        audio=wait(tts,195);assert audio['status']=='succeeded',audio
        renders=RenderTasks(args.runtime_root,root,tts)
        task=renders.start(audio['id'],first_avatar['id'],args.render_profile)
        try:renders.start(audio['id'],first_avatar['id']);raise AssertionError('重复视频任务被接受')
        except Conflict:report['checks']['duplicate_rejected']=True
        success=wait(renders,620);assert success['status']=='succeeded',success
        assert success['result']['render_profile']==args.render_profile
        assert renders.video_path(success['id']).is_file()
        report['first_result']=success['result'];report['checks']['real_tts_to_render_with_resident_tts']=True
        renders.close();renders=RenderTasks(args.runtime_root,root,tts)
        assert renders.video_path(success['id']).is_file();report['checks']['reopen_retains_valid_result']=True
        task=renders.start(audio['id'],first_avatar['id'],args.render_profile);process=renders.process
        cancelled=renders.cancel(task['id'])
        assert cancelled['status']=='cancelled' and 'result' not in cancelled and process.poll() is not None
        assert not (renders.jobs/task['id']/'output.mp4').exists()
        report['checks']['cancel_terminates_without_accepted_result']=True
        task=renders.start(audio['id'],first_avatar['id'],args.render_profile);recovered=wait(renders,620)
        assert recovered['status']=='succeeded',recovered
        report['checks']['new_render_after_cancel']=True
        renders.start(audio['id'],first_avatar['id'],args.render_profile)
        avatars.select(second_avatar['id'])
        # Do not poll state: let the real worker finish to exercise late-result rejection.
        renders.monitor.join(timeout=620)
        assert not renders.monitor.is_alive()
        stale=renders.state();assert stale['status']=='failed' and 'result' not in stale,stale
        assert not (renders.jobs/stale['id']/'output.mp4').exists()
        report['checks']['real_late_result_rejected_after_avatar_change']=True
        avatars.select(first_avatar['id']);renders.close();tts.close()
        assert renders.process is None and tts.process is None
        report.update(status='passed',workers_closed=True)
    except Exception as error:report.update(error_type=type(error).__name__,error=str(error))
    finally:
        if renders:renders.close()
        if tts:tts.close()
        (root/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'report':str(root/'result.json'),'error':report.get('error')},ensure_ascii=False))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
