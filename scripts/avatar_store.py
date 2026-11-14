"""Owned compatible avatar assets; never register a mutable external directory."""
from contextlib import closing
from ast import literal_eval
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import uuid


class AvatarError(ValueError):
    pass


def digest(path):
    with Path(path).open('rb') as stream:
        value = hashlib.sha256()
        for block in iter(lambda: stream.read(1024*1024), b''):
            value.update(block)
    return value.hexdigest()


class AvatarStore:
    def __init__(self, directory):
        self.root = (Path(directory)/'avatars').resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root/'avatars.sqlite3'
        with closing(sqlite3.connect(self.path)) as db, db:
            if db.execute('PRAGMA user_version').fetchone()[0] not in (0, 1):
                raise AvatarError('不支持的形象数据库版本')
            db.executescript('''CREATE TABLE IF NOT EXISTS avatars(
                id TEXT PRIMARY KEY,name TEXT NOT NULL,frames INTEGER NOT NULL,
                width INTEGER NOT NULL,height INTEGER NOT NULL,manifest_sha256 TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS selection(singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                avatar_id TEXT NOT NULL REFERENCES avatars(id)); PRAGMA user_version=1;''')
        self._cleanup_deleted_directories()

    def _cleanup_deleted_directories(self):
        for target in self.root.glob('.deleting-*'):
            try:
                if target.is_dir() and target.resolve().parent == self.root:
                    shutil.rmtree(target)
            except OSError:
                pass

    def _directory(self, avatar_id):
        try:
            if not isinstance(avatar_id, str) or str(uuid.UUID(avatar_id)) != avatar_id:
                raise ValueError()
        except ValueError:
            raise AvatarError('形象ID无效') from None
        target = (self.root/avatar_id).resolve()
        if target.parent != self.root:
            raise AvatarError('形象路径越界')
        return target

    def list(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute('SELECT * FROM avatars ORDER BY rowid')]

    def identity(self, avatar_id):
        """Verify selection identity; frame bytes must still be verified on use."""
        directory = self._directory(avatar_id)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.row_factory = sqlite3.Row
            row = db.execute('SELECT * FROM avatars WHERE id=?', (avatar_id,)).fetchone()
        if row is None:
            raise AvatarError('形象不存在')
        record = dict(row)
        try:
            manifest_path = directory/'manifest.json'
            if digest(manifest_path) != record['manifest_sha256']:
                raise AvatarError('形象清单已变化，请重新导入')
        except OSError:
            raise AvatarError('形象清单缺失，请重新导入') from None
        return record

    def get(self, avatar_id):
        record = self.identity(avatar_id)
        directory = self._directory(avatar_id)
        try:
            manifest_path = directory/'manifest.json'
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            for relative, expected in manifest['files'].items():
                path = (directory/relative).resolve()
                path.relative_to(directory)
                if digest(path) != expected:
                    raise AvatarError('形象素材已变化，请重新导入')
        except (OSError, KeyError, json.JSONDecodeError):
            raise AvatarError('形象素材缺失或清单损坏，请重新导入') from None
        return record

    def import_prepared(self, source, name):
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
            raise AvatarError('形象名称须为1至100字')
        source = Path(source)
        if not source.is_absolute() or not source.is_dir():
            raise AvatarError('请选择已有形象目录的绝对路径')
        files = sorted((source/'frames').glob('*.jpg'))
        if not 1 <= len(files) <= 6000:
            raise AvatarError('形象须包含1至6000帧')
        avatar_id = str(uuid.uuid4())
        target = self._directory(avatar_id)
        target.mkdir()
        registered = False
        total = 0
        hashes = {}
        try:
            import cv2
            dimensions = None
            face_frames = 0
            multi_face_frames = 0
            longest_no_face = current_no_face = 0
            for index, frame_path in enumerate(files):
                if frame_path.name != f'{index:06d}.jpg':
                    raise AvatarError('形象帧编号必须从000000连续排列')
                position_path = source/'positions'/f'{index:06d}.txt'
                for path in (frame_path, position_path):
                    resolved = path.resolve(strict=True)
                    resolved.relative_to(source.resolve())
                    total += path.stat().st_size
                    if total > 1024**3:
                        raise AvatarError('形象素材超过1GiB')
                    relative = path.relative_to(source).as_posix()
                    output = target/relative
                    output.parent.mkdir(parents=True, exist_ok=True)
                    before = digest(path)
                    shutil.copyfile(path, output)
                    if digest(output) != before or digest(path) != before:
                        raise AvatarError('源形象正在变化，请停止修改后重试')
                    hashes[relative] = before
                frame = cv2.imread(str(target/'frames'/frame_path.name))
                if frame is None:
                    raise AvatarError('形象帧无法解码')
                height, width = frame.shape[:2]
                if dimensions is None:
                    dimensions = (width, height)
                if dimensions != (width, height):
                    raise AvatarError('形象各帧尺寸不一致')
                metadata = {}
                for line in (target/'positions'/position_path.name).read_text(encoding='utf-8').splitlines():
                    key, separator, value = line.partition(':')
                    if separator:
                        metadata[key.strip()] = literal_eval(value.strip())
                if metadata.get('fps') != 25 or metadata.get('width') != width or metadata.get('height') != height:
                    raise AvatarError('形象须为25fps且位置记录与帧尺寸一致')
                if metadata.get('is_no_face') is False:
                    box = metadata.get('bounding_box')
                    if not isinstance(box, list) or len(box) != 4 or not all(type(v) in (int, float) for v in box):
                        raise AvatarError('形象人脸位置无效')
                    if box[1] <= box[0] or box[3] <= box[2]:
                        raise AvatarError('形象人脸位置范围无效')
                    if box[0] < 0 or box[2] < 0 or box[1] > height or box[3] > width:
                        raise AvatarError('形象人脸位置超出画面')
                    count = metadata.get('face_count', 1)
                    if type(count) is not int or count < 1:
                        raise AvatarError('形象人脸数量记录无效')
                    if count > 1:
                        multi_face_frames += 1
                    face_frames += 1
                    current_no_face = 0
                else:
                    current_no_face += 1
                    longest_no_face = max(longest_no_face, current_no_face)
            if not face_frames:
                raise AvatarError('形象中没有可驱动的人脸')
            if multi_face_frames:
                raise AvatarError('形象视频存在多人脸，请只保留一个人物')
            if face_frames / len(files) < .8:
                raise AvatarError('形象可驱动人脸帧不足80%')
            if longest_no_face > 12:
                raise AvatarError('形象连续超过0.48秒未检测到人脸')
            for asset_name in ('normalized_video.mp4', 'model_info.yaml'):
                path = source/asset_name
                if path.exists():
                    path.resolve(strict=True).relative_to(source.resolve())
                    total += path.stat().st_size
                    if total > 1024**3:
                        raise AvatarError('形象素材超过1GiB')
                    before = digest(path)
                    shutil.copyfile(path, target/asset_name)
                    if digest(target/asset_name)!=before or digest(path)!=before:
                        raise AvatarError('源形象正在变化，请停止修改后重试')
                    hashes[asset_name] = before
            shutil.copyfile(target/'frames/000000.jpg', target/'sample.jpg')
            hashes['sample.jpg'] = digest(target/'sample.jpg')
            (target/'manifest.json').write_text(json.dumps({'version': 1, 'files': hashes}, sort_keys=True), encoding='utf-8')
            with closing(sqlite3.connect(self.path)) as db, db:
                db.execute('INSERT INTO avatars VALUES(?,?,?,?,?,?)',
                    (avatar_id, name.strip(), len(files), *dimensions, digest(target/'manifest.json')))
            registered = True
            return self.get(avatar_id)
        except (OSError, SyntaxError, TypeError) as error:
            raise AvatarError('形象导入失败，请检查帧、位置记录及文件权限') from error
        finally:
            if not registered and target.resolve().parent == self.root:
                shutil.rmtree(target)

    def select(self, avatar_id):
        self.get(avatar_id)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('INSERT OR REPLACE INTO selection VALUES(1,?)', (avatar_id,))

    def selected(self):
        avatar_id=self.selected_id()
        if avatar_id:self.get(avatar_id)
        return avatar_id

    def selected_id(self):
        """Selection metadata only; callers must validate assets with get before use."""
        with closing(sqlite3.connect(self.path)) as db, db:
            row = db.execute('SELECT avatar_id FROM selection WHERE singleton=1').fetchone()
        return row[0] if row else None

    def directory(self, avatar_id):
        self.get(avatar_id)
        return self._directory(avatar_id)

    def sample(self, avatar_id):
        return (self.directory(avatar_id)/'sample.jpg').read_bytes()

    def delete(self, avatar_id):
        self.get(avatar_id)
        if self.selected_id() == avatar_id:
            raise AvatarError('当前选中形象不能删除，请先选择其他形象')
        target = self._directory(avatar_id)
        tombstone = self.root / f'.deleting-{avatar_id}-{uuid.uuid4().hex}'
        if tombstone.resolve().parent != self.root:
            raise AvatarError('形象删除路径越界')
        os.replace(target, tombstone)
        try:
            with closing(sqlite3.connect(self.path)) as db, db:
                deleted = db.execute('DELETE FROM avatars WHERE id=?', (avatar_id,)).rowcount
                if deleted != 1:
                    raise AvatarError('形象不存在')
        except Exception:
            os.replace(tombstone, target)
            raise
        cleanup_pending = False
        try:
            shutil.rmtree(tombstone)
        except OSError:
            cleanup_pending = True
        return {'id': avatar_id, 'cleanup_pending': cleanup_pending}
