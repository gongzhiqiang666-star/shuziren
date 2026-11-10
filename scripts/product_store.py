"""Single-machine product/script persistence with immutable generation snapshots."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import uuid


class ProductError(ValueError):
    pass


class Conflict(ProductError):
    pass


def text(value, label, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ProductError(label + "不能为空或超出长度限制")
    return value.strip()


def index_value(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ProductError("商品编号必须为整数或整数字符串")
    try:
        result = int(value)
    except ValueError:
        raise ProductError("商品编号必须为整数或整数字符串") from None
    if not -(2**63) <= result < 2**63:
        raise ProductError("商品编号超出范围")
    return result


class ProductStore:
    def __init__(self, directory):
        self.path = Path(directory) / "products.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2):
                raise ProductError("不支持的商品数据库版本")
            db.executescript('''
                CREATE TABLE IF NOT EXISTS products (
                    id TEXT PRIMARY KEY, product_index INTEGER NOT NULL UNIQUE,
                    legacy_index TEXT NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL,
                    extra TEXT NOT NULL, version INTEGER NOT NULL CHECK(version>0));
                CREATE TABLE IF NOT EXISTS scripts (
                    id TEXT PRIMARY KEY, product_id TEXT NOT NULL REFERENCES products(id),
                    product_version INTEGER NOT NULL, snapshot TEXT NOT NULL,
                    text TEXT NOT NULL, source TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
                CREATE TABLE IF NOT EXISTS selection (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    product_id TEXT NOT NULL REFERENCES products(id));
            ''')
            db.execute('BEGIN IMMEDIATE')
            columns = {row[1] for row in db.execute('PRAGMA table_info(scripts)')}
            if 'parent_script_id' not in columns:
                db.execute('ALTER TABLE scripts ADD COLUMN parent_script_id TEXT REFERENCES scripts(id)')
            db.execute('PRAGMA user_version=2')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def decode(row):
        if row is None:
            raise ProductError("商品不存在")
        value = dict(row)
        value["product_index"] = json.loads(value.pop("legacy_index"))
        value["extra"] = json.loads(value["extra"])
        return value

    def list(self):
        with self.connect() as db:
            return [self.decode(row) for row in db.execute("SELECT * FROM products ORDER BY rowid")]

    def get(self, product_id):
        with self.connect() as db:
            return self.decode(db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone())

    def save(self, *, title, content, product_index, product_id=None, version=None, extra=None):
        title, content = text(title, "商品名称", 200), text(content, "商品信息", 50000)
        numeric = index_value(product_index)
        if product_id is not None and (type(version) is not int or version < 1):
            raise ProductError("编辑商品必须提供有效版本")
        if extra is not None and not isinstance(extra, dict):
            raise ProductError("扩展字段必须为对象")
        encoded_extra = json.dumps(extra, ensure_ascii=False, allow_nan=False) if extra is not None else None
        try:
            with self.connect() as db:
                if product_id is None:
                    if version is not None:
                        raise ProductError("新商品不能指定版本")
                    product_id = str(uuid.uuid4())
                    db.execute("INSERT INTO products VALUES(?,?,?,?,?,?,1)",
                               (product_id, numeric, json.dumps(product_index), title, content, encoded_extra or '{}'))
                else:
                    changed = db.execute('''UPDATE products SET product_index=?,legacy_index=?,title=?,content=?,
                        extra=COALESCE(?,extra),version=version+1 WHERE id=? AND version=?''',
                        (numeric, json.dumps(product_index), title, content, encoded_extra, product_id, version))
                    if changed.rowcount != 1:
                        raise Conflict("商品已修改或不存在，请重新读取")
                return self.decode(db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone())
        except sqlite3.IntegrityError:
            raise Conflict("商品编号已存在") from None

    def select(self, product_id):
        with self.connect() as db:
            self.decode(db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone())
            db.execute("INSERT OR REPLACE INTO selection VALUES(1,?)", (product_id,))

    def selected(self):
        with self.connect() as db:
            row = db.execute("SELECT product_id FROM selection WHERE singleton=1").fetchone()
            return row[0] if row else None

    def add_script(self, snapshot, script, source="manual", parent_script_id=None):
        script = text(script, "话术", 100000)
        if source not in {"manual", "llm"}:
            raise ProductError("未知话术来源")
        if not isinstance(snapshot, dict) or not isinstance(snapshot.get("id"), str):
            raise ProductError("商品快照无效")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self.decode(db.execute("SELECT * FROM products WHERE id=?", (snapshot["id"],)).fetchone())
            if current != snapshot:
                raise Conflict("商品内容已变更，请重新生成或确认话术")
            if parent_script_id is not None:
                if not isinstance(parent_script_id, str) or source != 'manual':
                    raise ProductError('修改稿来源无效')
                parent = db.execute('SELECT product_id FROM scripts WHERE id=?',(parent_script_id,)).fetchone()
                if not parent or parent[0] != current['id']:
                    raise ProductError('原稿不存在或不属于当前商品')
            script_id = str(uuid.uuid4())
            db.execute("INSERT INTO scripts(id,product_id,product_version,snapshot,text,source,parent_script_id) VALUES(?,?,?,?,?,?,?)",
                       (script_id, current["id"], current["version"], json.dumps(current, ensure_ascii=False), script, source,parent_script_id))
            return script_id

    def scripts(self, product_id):
        with self.connect() as db:
            self.decode(db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone())
            result = []
            for row in db.execute("SELECT * FROM scripts WHERE product_id=? ORDER BY rowid", (product_id,)):
                value = dict(row)
                value["snapshot"] = json.loads(value["snapshot"])
                result.append(value)
            return result
