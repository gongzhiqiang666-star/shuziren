"""Single-machine product/script persistence with immutable generation snapshots."""
from contextlib import contextmanager
import csv
import io
import json
from datetime import date, datetime, timezone
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


def product_prompt_info(snapshot, *, now=None):
    """Project a versioned product into the facts permitted in a prompt."""
    extra = snapshot.get("extra") or {}
    if "product_facts" not in extra:
        return {"title": snapshot["title"], "content": snapshot["content"]}
    now = datetime.now(timezone.utc) if now is None else now
    facts = extra["product_facts"]
    verified = {}
    if isinstance(facts, dict):
        for name, fact in facts.items():
            if not isinstance(fact, dict) or fact.get("status") != "verified" or not fact.get("source"):
                continue
            try:
                expires = fact.get("expires_at")
                if expires is not None and datetime.fromisoformat(expires.replace("Z", "+00:00")) <= now:
                    continue
            except (AttributeError, TypeError, ValueError):
                continue
            if fact.get("value") is not None:
                verified[name] = fact["value"]
    return {"title": snapshot["title"], "content": json.dumps(verified, ensure_ascii=False)}


def script_facts_current(product, created_at):
    if "product_facts" not in product["extra"]:
        return True
    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    return product_prompt_info(product, now=created) == product_prompt_info(product)


def product_fact_deadline(product):
    now = datetime.now(timezone.utc)
    names = json.loads(product_prompt_info(product, now=now)["content"]) if (
        "product_facts" in (product.get("extra") or {})) else {}
    facts = (product.get("extra") or {}).get("product_facts", {})
    deadlines = [datetime.fromisoformat(facts[name]["expires_at"].replace("Z", "+00:00")).timestamp()
                 for name in names if facts[name].get("expires_at") is not None]
    return min(deadlines, default=None)


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
            if version not in (0, 1, 2, 3):
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
                CREATE TABLE IF NOT EXISTS script_selection (
                    product_id TEXT PRIMARY KEY REFERENCES products(id),
                    script_id TEXT NOT NULL REFERENCES scripts(id));
                CREATE TABLE IF NOT EXISTS live_rotation_events (
                    session_id TEXT NOT NULL, task_id TEXT NOT NULL,
                    product_id TEXT NOT NULL, product_version INTEGER NOT NULL,
                    script_id TEXT NOT NULL, segment_index INTEGER NOT NULL,
                    completed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                    PRIMARY KEY(session_id, task_id));
                CREATE TABLE IF NOT EXISTS live_sessions (
                    session_id TEXT PRIMARY KEY, requested_at REAL NOT NULL,
                    started_at REAL, ended_at REAL, status TEXT NOT NULL,
                    frames INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS live_control_events (
                    session_id TEXT NOT NULL, revision INTEGER NOT NULL, manual INTEGER NOT NULL,
                    occurred_at REAL NOT NULL, PRIMARY KEY(session_id, revision));
                CREATE TABLE IF NOT EXISTS product_business_metrics (
                    product_id TEXT NOT NULL REFERENCES products(id),
                    source TEXT NOT NULL, period_start TEXT NOT NULL, period_end TEXT NOT NULL,
                    scope TEXT NOT NULL, clicks INTEGER, orders INTEGER, refunds INTEGER, stock INTEGER,
                    PRIMARY KEY(product_id, source, period_start, period_end, scope));
            ''')
            db.execute('BEGIN IMMEDIATE')
            columns = {row[1] for row in db.execute('PRAGMA table_info(scripts)')}
            if 'parent_script_id' not in columns:
                db.execute('ALTER TABLE scripts ADD COLUMN parent_script_id TEXT REFERENCES scripts(id)')
            event_columns = {row[1] for row in db.execute('PRAGMA table_info(live_rotation_events)')}
            for column in ('sample_start', 'sample_end'):
                if column not in event_columns:
                    db.execute(f'ALTER TABLE live_rotation_events ADD COLUMN {column} INTEGER')
            db.execute('PRAGMA user_version=3')

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

    def save_business_metrics(self, product_id, *, source, period_start, period_end, scope,
                              clicks=None, orders=None, refunds=None, stock=None):
        row = self._business_metric_row(product_id, source=source, period_start=period_start,
                                        period_end=period_end, scope=scope, clicks=clicks,
                                        orders=orders, refunds=refunds, stock=stock)
        self.get(product_id)
        self._write_business_metrics([row])

    @staticmethod
    def _business_metric_row(product_id, *, source, period_start, period_end, scope,
                             clicks=None, orders=None, refunds=None, stock=None):
        source = text(source, '数据来源', 120)
        scope = text(scope, '统计口径', 500)
        try:
            start, end = date.fromisoformat(period_start), date.fromisoformat(period_end)
            if start.isoformat() != period_start or end.isoformat() != period_end or start > end:
                raise ValueError
        except (TypeError, ValueError):
            raise ProductError('请填写有效的起止日期，格式为 YYYY-MM-DD') from None
        counts = (clicks, orders, refunds, stock)
        if any(count is not None and (type(count) is not int or not 0 <= count < 2**63) for count in counts):
            raise ProductError('点击、订单、退款和库存须为非负整数或留空')
        return product_id, source, period_start, period_end, scope, *counts

    def import_business_metrics(self, product_id, content):
        if not isinstance(content, str) or not content.strip():
            raise ProductError('请选择非空 CSV 报表')
        self.get(product_id)
        required = {'source', 'period_start', 'period_end', 'scope'}
        counts = {'clicks': '点击', 'orders': '订单', 'refunds': '退款', 'stock': '库存'}
        rows, keys = [], set()
        try:
            reader = csv.DictReader(io.StringIO(content.removeprefix('\ufeff'), newline=''), strict=True)
            fields = reader.fieldnames or []
            if len(fields) != len(set(fields)) or not required <= set(fields) <= required.union(counts):
                raise ProductError('CSV 表头须包含 source、period_start、period_end、scope')
            for values in reader:
                try:
                    if None in values or any(value is None for value in values.values()):
                        raise ValueError('列数与表头不一致')
                    for name, label in counts.items():
                        value = values.get(name, '').strip()
                        if value and (len(value) > 19 or not value.isascii() or not value.isdigit()):
                            raise ValueError(f'{label}须为非负整数或留空')
                        values[name] = int(value) if value else None
                    row = self._business_metric_row(product_id, **values)
                    if row[:5] in keys:
                        raise ValueError('报表内的来源、日期和口径重复')
                    keys.add(row[:5])
                    rows.append(row)
                except ValueError as error:
                    raise ProductError(f'CSV 第 {reader.line_num} 行：{error}') from None
                if len(rows) > 1000:
                    raise ProductError('每次最多导入 1000 行经营数据')
        except csv.Error as error:
            raise ProductError(f'CSV 格式无效：{error}') from None
        if not rows:
            raise ProductError('CSV 中没有经营数据行')
        self._write_business_metrics(rows)
        return len(rows)

    def _write_business_metrics(self, rows):
        with self.connect() as db:
            db.executemany("""
                INSERT INTO product_business_metrics
                    (product_id, source, period_start, period_end, scope, clicks, orders, refunds, stock)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(product_id, source, period_start, period_end, scope) DO UPDATE SET
                    clicks=excluded.clicks, orders=excluded.orders, refunds=excluded.refunds, stock=excluded.stock
            """, rows)

    def business_metrics(self, product_id):
        self.get(product_id)
        with self.connect() as db:
            rows = db.execute("""
                SELECT * FROM product_business_metrics WHERE product_id = ?
                ORDER BY period_end DESC, period_start DESC, source, scope
            """, (product_id,)).fetchall()
        return [dict(row) for row in rows]

    def record_live_session(self, session_id, requested_at, *, started_at=None, ended_at=None,
                            status='preparing', frames=0):
        with self.connect() as db:
            db.execute("""
                INSERT INTO live_sessions
                    (session_id, requested_at, started_at, ended_at, status, frames)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    started_at = excluded.started_at, ended_at = excluded.ended_at,
                    status = excluded.status, frames = excluded.frames
                WHERE live_sessions.ended_at IS NULL
            """, (session_id, requested_at, started_at, ended_at, status, frames))

    def record_live_control(self, session_id, revision, manual, occurred_at):
        with self.connect() as db:
            db.execute("""
                INSERT INTO live_control_events (session_id, revision, manual, occurred_at)
                VALUES (?, ?, ?, ?) ON CONFLICT(session_id, revision) DO NOTHING
            """, (session_id, revision, manual, occurred_at))

    def live_control_events(self, session_id):
        with self.connect() as db:
            rows = db.execute("""
                SELECT revision, manual, occurred_at
                FROM live_control_events WHERE session_id = ? ORDER BY revision
            """, (session_id,)).fetchall()
        return [{**dict(row), 'manual': bool(row['manual'])} for row in rows]

    def live_session_record(self, session_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM live_sessions WHERE session_id = ?', (session_id,)).fetchone()
        return dict(row) if row is not None else None

    def recent_live_sessions(self):
        with self.connect() as db:
            rows = db.execute('SELECT * FROM live_sessions ORDER BY requested_at DESC, rowid DESC LIMIT 100').fetchall()
        return [dict(row) for row in rows]

    def record_rotation_completion(self, session_id, task_id, item, segment_index, *,
                                   sample_start=None, sample_end=None):
        with self.connect() as db:
            db.execute("""
                INSERT INTO live_rotation_events
                    (session_id, task_id, product_id, product_version, script_id, segment_index, sample_start, sample_end)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, task_id) DO NOTHING
            """, (session_id, task_id, item['product_id'], item['product_version'],
                  item['script_id'], segment_index, sample_start, sample_end))

    def rotation_events(self, session_id, *, after=0, product_id=None, task_id=None):
        with self.connect() as db:
            rows = db.execute("""
                SELECT rowid AS cursor, session_id, task_id, product_id, product_version,
                       script_id, segment_index, completed_at, sample_start, sample_end
                FROM live_rotation_events
                WHERE session_id = ? AND rowid > ?
                  AND (? IS NULL OR product_id = ?)
                  AND (? IS NULL OR task_id = ?)
                ORDER BY rowid LIMIT 100
            """, (session_id, after, product_id, product_id, task_id, task_id)).fetchall()
        return [dict(row) for row in rows]

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

    def save(self, *, title, content, product_index, product_id=None, version=None, extra=None,
             product_facts=None):
        title, content = text(title, "商品名称", 200), text(content, "商品信息", 50000)
        numeric = index_value(product_index)
        if product_id is not None and (type(version) is not int or version < 1):
            raise ProductError("编辑商品必须提供有效版本")
        if extra is not None and not isinstance(extra, dict):
            raise ProductError("扩展字段必须为对象")
        if product_facts is not None:
            if not isinstance(product_facts, dict):
                raise ProductError("商品事实必须为对象")
            for name, fact in product_facts.items():
                text(name, "事实名称", 100)
                if not isinstance(fact, dict) or fact.get("status") not in ("verified", "unknown"):
                    raise ProductError("商品事实必须标明已核对或未知")
                if fact["status"] == "verified":
                    text(fact.get("source"), "事实来源", 500)
                    if fact.get("value") is None:
                        raise ProductError("已核对的商品事实必须有值")
                if fact.get("expires_at") is not None:
                    try:
                        expires = datetime.fromisoformat(fact["expires_at"].replace("Z", "+00:00"))
                        if expires.tzinfo is None:
                            raise ValueError("missing timezone")
                    except (AttributeError, TypeError, ValueError):
                        raise ProductError("商品事实有效期必须含时区") from None
            if extra is None and product_id is not None:
                extra = self.get(product_id)["extra"]
            extra = {**(extra or {}), "product_facts": product_facts}
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

    def add_script(self, snapshot, script, source="manual", parent_script_id=None,
                   *, expected_prompt_info=None):
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
            if expected_prompt_info is not None and expected_prompt_info != product_prompt_info(current):
                raise Conflict("生成期间商品事实已到期，请重新生成")
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

    def select_script(self, product_id, script_id):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            product=self.decode(db.execute('SELECT * FROM products WHERE id=?',(product_id,)).fetchone())
            script=db.execute('SELECT product_id,product_version,created_at FROM scripts WHERE id=?',(script_id,)).fetchone()
            if not script or script['product_id']!=product_id:
                raise ProductError('话术不存在或不属于当前商品')
            if script['product_version']!=product['version']:
                raise Conflict('历史话术不能直接选用，请按当前商品事实修改并保存')
            if not script_facts_current(product, script['created_at']):
                raise Conflict('话术所用的商品事实已到期，请更新话术')
            db.execute('INSERT OR REPLACE INTO script_selection VALUES(?,?)',(product_id,script_id))

    def selected_script(self, product_id):
        with self.connect() as db:
            row=db.execute('''SELECT s.id, s.created_at, s.snapshot FROM script_selection choice
                JOIN scripts s ON s.id=choice.script_id JOIN products p ON p.id=choice.product_id
                WHERE p.id=? AND s.product_id=p.id AND s.product_version=p.version''',(product_id,)).fetchone()
            if row and script_facts_current(json.loads(row['snapshot']), row['created_at']):
                return row['id']
            return None
