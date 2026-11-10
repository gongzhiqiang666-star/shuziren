"""Owned reference voices: normalize media, pair transcript, verify fingerprints."""
import hashlib
from array import array
import math
import sys
from pathlib import Path
import shutil
import sqlite3
import subprocess
import uuid
import wave


class VoiceError(ValueError):
    pass


def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class VoiceStore:
    def __init__(self, directory):
        self.root=(Path(directory)/'voices').resolve()
        self.root.mkdir(parents=True,exist_ok=True)
        self.path=self.root/'voices.sqlite3'
        with sqlite3.connect(self.path) as db:
            version=db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0,1): raise VoiceError('不支持的音色数据库版本')
            db.executescript('''CREATE TABLE IF NOT EXISTS voices(
                id TEXT PRIMARY KEY,name TEXT NOT NULL,transcript TEXT NOT NULL,
                audio_sha256 TEXT NOT NULL,text_sha256 TEXT NOT NULL,duration REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS selection(singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                voice_id TEXT NOT NULL REFERENCES voices(id)); PRAGMA user_version=1;''')

    def _directory(self, voice_id):
        if not isinstance(voice_id,str): raise VoiceError('音色ID无效')
        try:
            if str(uuid.UUID(voice_id))!=voice_id: raise ValueError()
        except ValueError: raise VoiceError('音色ID无效') from None
        target=(self.root/voice_id).resolve()
        if target.parent!=self.root: raise VoiceError('音色路径越界')
        return target

    def list(self):
        with sqlite3.connect(self.path) as db:
            db.row_factory=sqlite3.Row
            return [dict(row) for row in db.execute('SELECT * FROM voices ORDER BY rowid')]

    def get(self, voice_id):
        directory=self._directory(voice_id)
        with sqlite3.connect(self.path) as db:
            db.row_factory=sqlite3.Row
            row=db.execute('SELECT * FROM voices WHERE id=?',(voice_id,)).fetchone()
        if row is None: raise VoiceError('音色不存在')
        record=dict(row)
        try:
            if (fingerprint(directory/'ref_audio.wav')!=record['audio_sha256']
                    or fingerprint(directory/'ref_text.txt')!=record['text_sha256']):
                raise VoiceError('参考音或文本已变化，请重新导入音色')
        except OSError: raise VoiceError('参考音或文本缺失，请重新导入音色') from None
        return record

    def import_audio(self, source, transcript, name, ffmpeg):
        if not isinstance(name,str) or not 1<=len(name.strip())<=100:
            raise VoiceError('音色名称须为1至100字')
        if not isinstance(transcript,str) or not 1<=len(transcript.strip())<=10000:
            raise VoiceError('参考音对应文本须为1至10000字')
        source=Path(source)
        if not source.is_absolute() or not source.is_file() or source.stat().st_size>100*1024*1024:
            raise VoiceError('请选择不超过100MiB的本机音频文件绝对路径')
        voice_id=str(uuid.uuid4());directory=self._directory(voice_id)
        directory.mkdir()
        registered=False
        try:
            audio=directory/'ref_audio.wav'
            result=subprocess.run([str(ffmpeg),'-nostdin','-y','-loglevel','error','-i',str(source),
                '-t','31','-vn','-ac','1','-ar','24000','-c:a','pcm_s16le',str(audio)],
                capture_output=True,timeout=60,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if result.returncode!=0: raise VoiceError('音频无法解码，请检查文件格式或内容')
            with wave.open(str(audio),'rb') as reader:
                duration=reader.getnframes()/reader.getframerate()
                if reader.getnchannels()!=1 or reader.getsampwidth()!=2 or reader.getframerate()!=24000:
                    raise VoiceError('参考音规范化参数不正确')
                samples=array('h',reader.readframes(reader.getnframes()))
                if sys.byteorder!='little': samples.byteswap()
            if not 1<=duration<=30: raise VoiceError('参考音须为1至30秒；超长音频不会静默截断导入')
            rms=math.sqrt(sum(value*value for value in samples)/len(samples))/32768
            if rms<.001: raise VoiceError('参考音无声或音量过低，请选择清晰的人声录音')
            text=directory/'ref_text.txt';text.write_text(transcript.strip(),encoding='utf-8')
            with sqlite3.connect(self.path) as db:
                db.execute('INSERT INTO voices VALUES(?,?,?,?,?,?)',(voice_id,name.strip(),transcript.strip(),
                    fingerprint(audio),fingerprint(text),duration))
            registered=True
            return self.get(voice_id)
        except (subprocess.TimeoutExpired,OSError,wave.Error) as error:
            raise VoiceError('音色导入失败，请检查媒体、FFmpeg或文件权限') from None
        finally:
            if not registered:
                # Only this call's generated UUID directory; never a source/user path.
                if directory.parent==self.root and directory.resolve().parent==self.root:
                    shutil.rmtree(directory)

    def select(self, voice_id):
        self.get(voice_id)
        with sqlite3.connect(self.path) as db:
            db.execute('INSERT OR REPLACE INTO selection VALUES(1,?)',(voice_id,))

    def selected(self):
        with sqlite3.connect(self.path) as db:
            row=db.execute('SELECT voice_id FROM selection WHERE singleton=1').fetchone()
        if row: self.get(row[0])
        return row[0] if row else None
