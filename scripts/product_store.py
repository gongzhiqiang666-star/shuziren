"""Single-machine product/script persistence with immutable generation snapshots."""
from contextlib import contextmanager
import csv
import hashlib
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
    verified = {name: fact["value"] for name, fact in verified_product_facts(snapshot, now=now).items()}
    return {"title": snapshot["title"], "content": json.dumps(verified, ensure_ascii=False)}


def verified_product_facts(snapshot, *, now=None):
    now = datetime.now(timezone.utc) if now is None else now
    facts = (snapshot.get("extra") or {}).get("product_facts")
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
                verified[name] = fact
    return verified


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
    PREPARATION_FIELDS = {
        'goal': '场次目标', 'audience': '目标人群', 'promotion': '活动条件',
        'stock': '库存条件', 'shipping': '发货条件', 'constraints': '本场限制',
    }
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
                CREATE TABLE IF NOT EXISTS product_after_sales (
                    product_id TEXT NOT NULL REFERENCES products(id), source TEXT NOT NULL,
                    period_start TEXT NOT NULL, period_end TEXT NOT NULL,
                    counts TEXT NOT NULL, PRIMARY KEY(product_id, source, period_start, period_end));
                CREATE TABLE IF NOT EXISTS sourcing_candidates (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, supplier TEXT NOT NULL, source TEXT NOT NULL,
                    observed_on TEXT NOT NULL, details TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sourcing_trials (
                    candidate_id TEXT PRIMARY KEY REFERENCES sourcing_candidates(id),
                    sample_evidence TEXT NOT NULL, trial_evidence TEXT NOT NULL,
                    cost_minor INTEGER, verdict TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sourcing_decisions (
                    candidate_id TEXT PRIMARY KEY REFERENCES sourcing_candidates(id), snapshot TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS promotion_spend (
                    product_id TEXT NOT NULL REFERENCES products(id), source TEXT NOT NULL,
                    period_start TEXT NOT NULL, period_end TEXT NOT NULL, campaign TEXT NOT NULL,
                    asset TEXT NOT NULL, spend_minor INTEGER NOT NULL, attribution TEXT,
                    PRIMARY KEY(product_id, source, period_start, period_end, campaign, asset));
                CREATE TABLE IF NOT EXISTS promotion_plans (
                    id TEXT PRIMARY KEY, product_id TEXT NOT NULL REFERENCES products(id),
                    snapshot TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS promotion_plan_actions (
                    plan_id TEXT NOT NULL REFERENCES promotion_plans(id), action TEXT NOT NULL,
                    occurred_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS product_after_sales_tasks (
                    product_id TEXT NOT NULL, source TEXT NOT NULL, period_start TEXT NOT NULL,
                    period_end TEXT NOT NULL, category TEXT NOT NULL, evidence_count INTEGER NOT NULL,
                    owner TEXT NOT NULL, goal TEXT NOT NULL,
                    PRIMARY KEY(product_id, source, period_start, period_end, category));
                CREATE TABLE IF NOT EXISTS live_preparation (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1), draft TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS live_lineup_baseline (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1), snapshot TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS live_lineup_trials (
                    session_id TEXT PRIMARY KEY REFERENCES live_sessions(session_id), snapshot TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS live_rotation_faults (
                    session_id TEXT NOT NULL, occurred_at REAL NOT NULL, reason TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS live_content_drafts (
                    session_id TEXT NOT NULL, task_id TEXT NOT NULL, body TEXT NOT NULL,
                    PRIMARY KEY(session_id, task_id),
                    FOREIGN KEY(session_id, task_id) REFERENCES live_rotation_events(session_id, task_id));
                CREATE TABLE IF NOT EXISTS live_content_schedule (
                    session_id TEXT NOT NULL, task_id TEXT NOT NULL, account TEXT NOT NULL,
                    audience TEXT NOT NULL, publish_at TEXT NOT NULL, planned_body TEXT NOT NULL,
                    PRIMARY KEY(session_id, task_id),
                    FOREIGN KEY(session_id, task_id) REFERENCES live_content_drafts(session_id, task_id));
                CREATE TABLE IF NOT EXISTS live_content_receipts (
                    session_id TEXT NOT NULL, task_id TEXT NOT NULL, account TEXT NOT NULL, publication_id TEXT NOT NULL,
                    PRIMARY KEY(session_id, task_id), UNIQUE(account, publication_id),
                    FOREIGN KEY(session_id, task_id) REFERENCES live_content_schedule(session_id, task_id));
                CREATE TABLE IF NOT EXISTS live_advice_acknowledgments (
                    session_id TEXT NOT NULL, advice TEXT NOT NULL, acknowledged_at REAL NOT NULL,
                    PRIMARY KEY(session_id, advice));
                CREATE TABLE IF NOT EXISTS live_advice_actions (
                    session_id TEXT NOT NULL, advice TEXT NOT NULL, action TEXT NOT NULL, occurred_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS live_improvement_tasks (
                    session_id TEXT NOT NULL, fault_id INTEGER NOT NULL,
                    owner TEXT NOT NULL, goal TEXT NOT NULL,
                    PRIMARY KEY(session_id, fault_id));
                CREATE TABLE IF NOT EXISTS live_queued_replies (
                    session_id TEXT NOT NULL, task_id TEXT NOT NULL, product_id TEXT NOT NULL,
                    product_version INTEGER NOT NULL, question TEXT NOT NULL, answer TEXT NOT NULL,
                    queued_at REAL NOT NULL, PRIMARY KEY(session_id, task_id));
                CREATE INDEX IF NOT EXISTS live_queued_replies_session_time
                    ON live_queued_replies(session_id, queued_at);
                CREATE TABLE IF NOT EXISTS live_reply_reviews (
                    session_id TEXT NOT NULL, task_id TEXT NOT NULL, verdict TEXT NOT NULL,
                    review_seconds INTEGER, PRIMARY KEY(session_id, task_id),
                    FOREIGN KEY(session_id, task_id) REFERENCES live_queued_replies(session_id, task_id));
                CREATE TABLE IF NOT EXISTS live_unqueued_replies (
                    session_id TEXT NOT NULL, product_id TEXT NOT NULL, product_version INTEGER NOT NULL,
                    question TEXT NOT NULL, status TEXT NOT NULL, reason TEXT NOT NULL, occurred_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS live_preparation_review (
                    revision TEXT PRIMARY KEY, review TEXT NOT NULL);
            ''')
            db.execute('BEGIN IMMEDIATE')
            if 'metrics' not in {row[1] for row in db.execute('PRAGMA table_info(sourcing_trials)')}:
                db.execute('ALTER TABLE sourcing_trials ADD COLUMN metrics TEXT')
            if 'revoked' not in {row[1] for row in db.execute('PRAGMA table_info(product_after_sales_tasks)')}:
                db.execute('ALTER TABLE product_after_sales_tasks ADD COLUMN revoked INTEGER NOT NULL DEFAULT 0')
            if 'withdrawn' not in {row[1] for row in db.execute('PRAGMA table_info(live_content_drafts)')}:
                db.execute('ALTER TABLE live_content_drafts ADD COLUMN withdrawn INTEGER NOT NULL DEFAULT 0')
            if 'revoked_at' not in {row[1] for row in db.execute('PRAGMA table_info(live_advice_acknowledgments)')}:
                db.execute('ALTER TABLE live_advice_acknowledgments ADD COLUMN revoked_at REAL')
            fault_columns = {row[1] for row in db.execute('PRAGMA table_info(live_rotation_faults)')}
            for column, kind in (('product_id', 'TEXT'), ('product_version', 'INTEGER'), ('script_id', 'TEXT')):
                if column not in fault_columns:
                    db.execute(f'ALTER TABLE live_rotation_faults ADD COLUMN {column} {kind}')
            if 'adopted' not in {row[1] for row in db.execute('PRAGMA table_info(live_improvement_tasks)')}:
                db.execute('ALTER TABLE live_improvement_tasks ADD COLUMN adopted INTEGER NOT NULL DEFAULT 0')
            columns = {row[1] for row in db.execute('PRAGMA table_info(scripts)')}
            if 'parent_script_id' not in columns:
                db.execute('ALTER TABLE scripts ADD COLUMN parent_script_id TEXT REFERENCES scripts(id)')
            if 'failure_reason' not in {row[1] for row in db.execute('PRAGMA table_info(live_sessions)')}:
                db.execute('ALTER TABLE live_sessions ADD COLUMN failure_reason TEXT')
            if 'played_at' not in {row[1] for row in db.execute('PRAGMA table_info(live_queued_replies)')}:
                db.execute('ALTER TABLE live_queued_replies ADD COLUMN played_at REAL')
            event_columns = {row[1] for row in db.execute('PRAGMA table_info(live_rotation_events)')}
            for column in ('sample_start', 'sample_end'):
                if column not in event_columns:
                    db.execute(f'ALTER TABLE live_rotation_events ADD COLUMN {column} INTEGER')
            if 'voice_id' not in event_columns:
                db.execute('ALTER TABLE live_rotation_events ADD COLUMN voice_id TEXT')
            if 'speech_provenance' not in event_columns:
                db.execute('ALTER TABLE live_rotation_events ADD COLUMN speech_provenance TEXT')
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

    def live_preparation(self):
        with self.connect() as db:
            row = db.execute('SELECT draft FROM live_preparation WHERE singleton=1').fetchone()
        draft = json.loads(row['draft']) if row else {'product_ids': [], **dict.fromkeys(self.PREPARATION_FIELDS, '')}
        missing = [label for key, label in self.PREPARATION_FIELDS.items() if not draft[key]]
        if not draft['product_ids']:
            missing.insert(0, '本场商品')
        return {'draft': draft, 'missing': missing}

    def save_live_preparation(self, *, product_ids, **conditions):
        if set(conditions) - self.PREPARATION_FIELDS.keys():
            raise ProductError('存在未知的直播准备字段')
        if not isinstance(product_ids, list) or any(not isinstance(item, str) for item in product_ids):
            raise ProductError('本场商品应为商品 ID 列表')
        if len(product_ids) != len(set(product_ids)):
            raise ProductError('本场商品不能重复')
        draft = {'product_ids': product_ids}
        for key, label in self.PREPARATION_FIELDS.items():
            value = conditions.get(key, '')
            if not isinstance(value, str) or len(value) > 2000:
                raise ProductError(label + '必须是 2000 字以内的文本')
            draft[key] = value.strip()
        for product_id in product_ids:
            self.get(product_id)
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO live_preparation VALUES (1, ?)',
                       (json.dumps(draft, ensure_ascii=False),))

    def live_lineup_baseline(self):
        with self.connect() as db:
            row = db.execute('SELECT snapshot FROM live_lineup_baseline WHERE singleton=1').fetchone()
        return json.loads(row['snapshot']) if row else None

    def capture_live_lineup_baseline(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT draft FROM live_preparation WHERE singleton=1').fetchone()
            draft = json.loads(row['draft']) if row else None
            if not draft or not draft['product_ids']:
                raise Conflict('请先保存包含商品的准备草稿')
            lineup = []
            for product_id in draft['product_ids']:
                product = db.execute('SELECT id, title, version FROM products WHERE id=?', (product_id,)).fetchone()
                if product is None:
                    raise Conflict('基线商品已不存在，请核对草稿')
                lineup.append(dict(product))
            baseline = {'draft': draft, 'lineup': lineup, 'captured_at': datetime.now(timezone.utc).isoformat()}
            db.execute('INSERT OR REPLACE INTO live_lineup_baseline VALUES (1, ?)',
                       (json.dumps(baseline, ensure_ascii=False),))
        return baseline

    def bind_live_lineup_trial(self, session_id):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            result = db.execute("""
                INSERT INTO live_lineup_trials
                SELECT session_id, snapshot FROM live_sessions CROSS JOIN live_lineup_baseline
                WHERE session_id=? AND started_at IS NOT NULL AND ended_at IS NOT NULL
                ON CONFLICT(session_id) DO NOTHING
            """, (session_id,))
            if not result.rowcount and not db.execute(
                    'SELECT 1 FROM live_lineup_trials WHERE session_id=?', (session_id,)).fetchone():
                raise Conflict('需要已留存的人工基线和已结束的试播场次')

    def build_live_preparation(self):
        preparation = self.live_preparation()
        if not preparation['draft']['product_ids']:
            raise ProductError('请先在准备草稿中保存本场商品')
        now = datetime.now(timezone.utc)
        items = []
        for product_id in preparation['draft']['product_ids']:
            product = self.get(product_id)
            facts = verified_product_facts(product, now=now)
            items.append({
                'product_id': product_id, 'product_version': product['version'], 'title': product['title'],
                'selling_points': [{'name': name, 'value': fact['value'], 'source': fact['source']}
                                   for name, fact in facts.items()],
                'faq': [{'question': f"{name}是什么？", 'answer': fact['value'], 'source': fact['source']}
                        for name, fact in facts.items()],
                'missing': [] if facts else ['补充并核对商品事实'],
                'assets': ['核对商品展示图或实拍视频'],
            })
        selected_ids = set(preparation['draft']['product_ids'])
        improvements = [task for task in self.live_improvements(adopted_only=True)
                        if task['product_id'] is None or task['product_id'] in selected_ids]
        package = {**preparation, 'items': items, 'improvements': improvements,
                   'after_sales_tasks': self.after_sales_tasks(preparation['draft']['product_ids'], current_only=True),
                   'segments': {
            'opening': '欢迎来到直播间，接下来为大家逐一介绍本场商品。',
            'transition': '接下来介绍下一件商品。',
            'closing': '感谢观看，本场商品介绍到这里。',
        }}
        revision = hashlib.sha256(json.dumps(package, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()
        with self.connect() as db:
            row = db.execute('SELECT review FROM live_preparation_review WHERE revision=?',
                             (revision,)).fetchone()
        return {**package, 'revision': revision, 'review': row['review'] if row else None}

    def save_live_preparation_review(self, revision, review):
        review = text(review, '准备包审阅稿', 100000)
        if revision != self.build_live_preparation()['revision']:
            raise Conflict('准备包内容已变化，请重新预览后保存')
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO live_preparation_review VALUES (?, ?)', (revision, review))

    def live_preparation_rotation(self, revision):
        package = self.build_live_preparation()
        if revision != package['revision']:
            raise Conflict('准备包内容已变化，请重新预览')
        if package['review'] is None:
            raise Conflict('请先保存准备包审阅稿')
        if len(package['items']) > 20:
            raise ProductError('商品轮播最多支持20件商品')
        items = []
        for item in package['items']:
            product_id = item['product_id']
            script_id = self.selected_script(product_id)
            if self.get(product_id)['version'] != item['product_version']:
                raise Conflict('商品版本已变化，请重新预览')
            items.append({**{key: item[key] for key in ('product_id', 'product_version', 'title', 'assets')},
                          'script_id': script_id})
        return {'revision': revision, 'items': items}

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
                        count = int(value) if value else None
                        if count is not None and count >= 2**63:
                            raise ValueError(f'{label}超出可记录范围')
                        values[name] = count
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

    def summarize_business_metrics(self, product_id, *, source, scope, period_start, period_end):
        key = self._business_metric_row(product_id, source=source, scope=scope,
                                        period_start=period_start, period_end=period_end)
        _, source, period_start, period_end, scope = key[:5]
        self.get(product_id)
        with self.connect() as db:
            rows = db.execute("""
                SELECT * FROM product_business_metrics
                WHERE product_id = ? AND source = ? AND scope = ?
                  AND period_end >= ? AND period_start <= ?
                ORDER BY period_start, period_end
            """, (product_id, source, scope, period_start, period_end)).fetchall()
        next_day = date.fromisoformat(period_start).toordinal()
        end_day = date.fromisoformat(period_end).toordinal()
        for row in rows:
            start = date.fromisoformat(row['period_start']).toordinal()
            end = date.fromisoformat(row['period_end']).toordinal()
            if start != next_day or end > end_day:
                raise ProductError('报表覆盖存在缺口、重叠或超出所选日期')
            next_day = end + 1
        if next_day != end_day + 1:
            raise ProductError('报表未完整覆盖所选日期')
        summary = {}
        for name in ('clicks', 'orders', 'refunds'):
            values = [row[name] for row in rows]
            summary[name] = None if None in values else sum(values)
        return {**summary, 'closing_stock': rows[-1]['stock']}

    def record_live_session(self, session_id, requested_at, *, started_at=None, ended_at=None,
                            status='preparing', frames=0, failure_reason=None):
        with self.connect() as db:
            db.execute("""
                INSERT INTO live_sessions
                    (session_id, requested_at, started_at, ended_at, status, frames, failure_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    started_at = excluded.started_at, ended_at = excluded.ended_at,
                    status = excluded.status, frames = excluded.frames, failure_reason = excluded.failure_reason
                WHERE live_sessions.ended_at IS NULL
            """, (session_id, requested_at, started_at, ended_at, status, frames, failure_reason))

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

    def live_session_report(self, session_id):
        with self.connect() as db:
            db.execute('BEGIN')
            session = db.execute('SELECT * FROM live_sessions WHERE session_id = ?', (session_id,)).fetchone()
            if session is None:
                raise ProductError('场次记录不存在')
            trial = db.execute('SELECT snapshot FROM live_lineup_trials WHERE session_id=?', (session_id,)).fetchone()
            products = db.execute("""
                SELECT product_id, product_version, script_id, COUNT(*) AS completed_segments,
                       MIN(completed_at) AS first_completed_at, MAX(completed_at) AS last_completed_at
                FROM live_rotation_events WHERE session_id = ?
                GROUP BY product_id, product_version, script_id ORDER BY MIN(rowid)
            """, (session_id,)).fetchall()
            controls = db.execute("""
                SELECT revision, manual, occurred_at FROM live_control_events
                WHERE session_id = ? ORDER BY revision
            """, (session_id,)).fetchall()
            faults = db.execute("""
                SELECT rowid AS event_id, occurred_at, reason, product_id, product_version, script_id
                FROM live_rotation_faults
                WHERE session_id = ? ORDER BY rowid
            """, (session_id,)).fetchall()
            replies = db.execute("""
                SELECT task_id, product_id, product_version, question, answer, queued_at, played_at,
                       verdict, review_seconds
                FROM live_queued_replies LEFT JOIN live_reply_reviews USING (session_id, task_id)
                WHERE session_id = ? ORDER BY live_queued_replies.rowid
            """, (session_id,)).fetchall()
            unqueued = db.execute("""
                SELECT rowid AS event_id, product_id, product_version, question, status, reason, occurred_at
                FROM live_unqueued_replies WHERE session_id=? ORDER BY rowid
            """, (session_id,)).fetchall()
            switches = db.execute("""
                WITH sequence AS (
                    SELECT rowid AS cursor, task_id, product_id, completed_at,
                           LAG(product_id) OVER (ORDER BY rowid) AS previous_product_id
                    FROM live_rotation_events WHERE session_id = ?
                )
                SELECT * FROM sequence WHERE previous_product_id <> product_id ORDER BY cursor
            """, (session_id,)).fetchall()
        return {
            'session': dict(session),
            'lineup_baseline': json.loads(trial['snapshot']) if trial else None,
            'products': [dict(row) for row in products],
            'controls': [{**dict(row), 'manual': bool(row['manual'])} for row in controls],
            'rotation_faults': [dict(row) for row in faults],
            'queued_replies': [dict(row) for row in replies],
            'unqueued_replies': [dict(row) for row in unqueued],
            'observed_product_switches': [dict(row) for row in switches],
            'missing': ['product_exposure', 'questions_and_answers', 'platform_product_switches',
                        'fault_events', 'attributed_sales'],
        }

    def record_unqueued_reply(self, session_id, product, question, status, reason, occurred_at):
        with self.connect() as db:
            db.execute('INSERT INTO live_unqueued_replies VALUES (?, ?, ?, ?, ?, ?, ?)',
                       (session_id, product['id'], product['version'], question, status, reason, occurred_at))

    def record_queued_reply(self, session_id, task_id, product, question, answer, queued_at):
        with self.connect() as db:
            db.execute('''INSERT OR IGNORE INTO live_queued_replies
                       (session_id, task_id, product_id, product_version, question, answer, queued_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)''',
                       (session_id, task_id, product['id'], product['version'], question, answer, queued_at))

    def record_reply_playback(self, session_id, task_id, played_at):
        with self.connect() as db:
            db.execute('UPDATE live_queued_replies SET played_at=? WHERE session_id=? AND task_id=? AND played_at IS NULL',
                       (played_at, session_id, task_id))

    def review_live_reply(self, session_id, task_id, verdict, review_seconds):
        if verdict not in ('correct', 'incorrect', 'uncertain'):
            raise ProductError('请选择答复复核结果')
        if review_seconds is not None and (type(review_seconds) is not int or not 0 <= review_seconds <= 86400):
            raise ProductError('复核用时须为 0 至 86400 秒的整数或未知')
        with self.connect() as db:
            result = db.execute("""
                INSERT INTO live_reply_reviews
                SELECT session_id, task_id, ?, ? FROM live_queued_replies WHERE session_id=? AND task_id=?
                ON CONFLICT(session_id, task_id) DO UPDATE SET
                    verdict=excluded.verdict, review_seconds=excluded.review_seconds
            """, (verdict, review_seconds, session_id, task_id))
            if not result.rowcount:
                raise ProductError('该场次没有对应的问答任务')

    def recent_repeated_live_questions(self, session_id, since):
        with self.connect() as db:
            rows = db.execute("""
                WITH recent AS (
                    SELECT product_id, TRIM(question) AS question, task_id, queued_at,
                           COUNT(*) OVER (PARTITION BY product_id, TRIM(question)) AS occurrences,
                           ROW_NUMBER() OVER (PARTITION BY product_id, TRIM(question)
                                              ORDER BY queued_at DESC, rowid DESC) AS position
                    FROM live_queued_replies WHERE session_id=? AND queued_at>=?
                )
                SELECT product_id, question, task_id, occurrences, queued_at AS last_queued_at
                FROM recent WHERE occurrences >= 2 AND position=1
                ORDER BY last_queued_at DESC, product_id, question LIMIT 5
            """, (session_id, since)).fetchall()
        return [dict(row) for row in rows]

    def record_rotation_fault(self, session_id, occurred_at, reason, *, item=None):
        item = item or {}
        with self.connect() as db:
            db.execute("""
                INSERT INTO live_rotation_faults
                    (session_id, occurred_at, reason, product_id, product_version, script_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (session_id, occurred_at, reason, item.get('product_id'),
                  item.get('product_version'), item.get('script_id')))

    def acknowledge_live_advice(self, session_id, advice, acknowledged_at):
        evidence = json.dumps(advice, sort_keys=True, ensure_ascii=False)
        with self.connect() as db:
            result = db.execute('''INSERT INTO live_advice_acknowledgments (session_id, advice, acknowledged_at)
                       VALUES (?, ?, ?) ON CONFLICT(session_id, advice) DO UPDATE SET
                       acknowledged_at=excluded.acknowledged_at, revoked_at=NULL
                       WHERE live_advice_acknowledgments.revoked_at IS NOT NULL''',
                       (session_id, evidence, acknowledged_at))
            if result.rowcount:
                db.execute('INSERT INTO live_advice_actions VALUES (?, ?, ?, ?)',
                           (session_id, evidence, 'acknowledge', acknowledged_at))

    def revoke_live_advice_acknowledgment(self, session_id, advice, revoked_at):
        evidence = json.dumps(advice, sort_keys=True, ensure_ascii=False)
        with self.connect() as db:
            result = db.execute('''UPDATE live_advice_acknowledgments SET revoked_at=?
                       WHERE session_id=? AND advice=? AND revoked_at IS NULL''',
                       (revoked_at, session_id, evidence))
            if result.rowcount:
                db.execute('INSERT INTO live_advice_actions VALUES (?, ?, ?, ?)',
                           (session_id, evidence, 'revoke', revoked_at))

    def live_advice_actions(self, session_id):
        with self.connect() as db:
            rows = db.execute('SELECT advice, action, occurred_at FROM live_advice_actions WHERE session_id=? ORDER BY rowid',
                              (session_id,)).fetchall()
        return [{**dict(row), 'advice': json.loads(row['advice'])} for row in rows]

    def live_advice_acknowledgments(self, session_id):
        with self.connect() as db:
            rows = db.execute("""
                SELECT advice, acknowledged_at, revoked_at FROM live_advice_acknowledgments
                WHERE session_id=? ORDER BY rowid
            """, (session_id,)).fetchall()
        return [{**dict(row), 'advice': json.loads(row['advice'])} for row in rows]

    def save_live_improvement(self, session_id, fault_id, owner, goal, adopted=False):
        owner = text(owner, '负责人', 120)
        goal = text(goal, '改进目标', 2000)
        if type(fault_id) is not int or not 0 < fault_id < 2**63:
            raise ProductError('轮播故障编号无效')
        if type(adopted) is not bool:
            raise ProductError('采用状态无效')
        with self.connect() as db:
            result = db.execute("""
                INSERT INTO live_improvement_tasks (session_id, fault_id, owner, goal, adopted)
                SELECT session_id, rowid, ?, ?, ? FROM live_rotation_faults WHERE session_id=? AND rowid=?
                ON CONFLICT(session_id, fault_id) DO UPDATE SET
                    owner=excluded.owner, goal=excluded.goal, adopted=excluded.adopted
            """, (owner, goal, adopted, session_id, fault_id))
            if not result.rowcount:
                raise ProductError('该场次没有对应的轮播故障记录')

    def live_improvements(self, session_id=None, *, adopted_only=False):
        with self.connect() as db:
            rows = db.execute("""
                SELECT task.session_id, task.fault_id, task.owner, task.goal, task.adopted,
                       fault.reason, fault.occurred_at, fault.product_id, fault.product_version, fault.script_id
                FROM live_improvement_tasks task
                JOIN live_rotation_faults fault ON fault.rowid=task.fault_id AND fault.session_id=task.session_id
                WHERE (? IS NULL OR task.session_id=?) AND (NOT ? OR task.adopted=1)
                ORDER BY task.fault_id
            """, (session_id, session_id, adopted_only)).fetchall()
        return [{**dict(row), 'adopted': bool(row['adopted'])} for row in rows]

    def record_rotation_completion(self, session_id, task_id, item, segment_index, *,
                                   sample_start=None, sample_end=None, voice_id=None, speech_provenance=None):
        with self.connect() as db:
            db.execute("""
                INSERT INTO live_rotation_events
                    (session_id, task_id, product_id, product_version, script_id, segment_index,
                     sample_start, sample_end, voice_id, speech_provenance)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, task_id) DO NOTHING
            """, (session_id, task_id, item['product_id'], item['product_version'],
                  item['script_id'], segment_index, sample_start, sample_end, voice_id,
                  json.dumps(speech_provenance) if speech_provenance else None))

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

    def live_content_source(self, session_id, task_id):
        with self.connect() as db:
            row = db.execute("""
                SELECT event.session_id, event.task_id, event.product_id, event.product_version,
                       event.script_id, event.segment_index, event.completed_at,
                       event.sample_start, event.sample_end, event.voice_id, event.speech_provenance,
                       script.snapshot, script.text AS script_text,
                       script.created_at AS script_created_at, product.version AS current_product_version
                FROM live_rotation_events event
                LEFT JOIN scripts script ON script.id=event.script_id AND script.product_id=event.product_id
                                        AND script.product_version=event.product_version
                LEFT JOIN products product ON product.id=event.product_id
                WHERE event.session_id=? AND event.task_id=?
            """, (session_id, task_id)).fetchone()
        if row is None:
            raise ProductError('该场次没有对应的口播完成记录')
        source = dict(row)
        provenance = source['speech_provenance']
        source['speech_provenance'] = json.loads(provenance) if provenance else None
        snapshot = source.pop('snapshot')
        source['product_snapshot'] = json.loads(snapshot) if snapshot else None
        created_at = source.pop('script_created_at')
        if not snapshot or not created_at:
            source['facts_review'] = 'source_missing'
        elif source['current_product_version'] != source['product_version']:
            source['facts_review'] = 'product_changed'
        elif not script_facts_current(source['product_snapshot'], created_at):
            source['facts_review'] = 'facts_changed'
        else:
            source['facts_review'] = 'version_current'
        source['segment'] = None
        if source['script_text'] is not None:
            from recovered.slice_content import slice_content

            segments = slice_content(source['script_text'])
            if not any(segment['type'] in {'assistant', 'pause'} for segment in segments):
                segments = [{'type': 'host', 'content': source['script_text']}]
            index = source['segment_index']
            if 0 <= index < len(segments) and segments[index]['type'] != 'pause':
                source['segment'] = segments[index]
        return source

    def live_content_draft_body(self, session_id, task_id):
        with self.connect() as db:
            row = db.execute('SELECT body FROM live_content_drafts WHERE session_id=? AND task_id=?',
                             (session_id, task_id)).fetchone()
        return row['body'] if row else None

    def live_content_schedule(self, session_id, task_id):
        with self.connect() as db:
            row = db.execute("""
                SELECT live_content_schedule.account, audience, publish_at, planned_body=body AS draft_matches,
                       publication_id, withdrawn
                FROM live_content_schedule JOIN live_content_drafts USING (session_id, task_id)
                LEFT JOIN live_content_receipts USING (session_id, task_id)
                WHERE session_id=? AND task_id=?
            """, (session_id, task_id)).fetchone()
        return {**dict(row), 'draft_matches': bool(row['draft_matches']), 'withdrawn': bool(row['withdrawn'])} if row else None

    def save_live_content_schedule(self, session_id, task_id, account, audience, publish_at):
        account = text(account, '发布账号', 120)
        audience = text(audience, '发布范围', 120)
        try:
            scheduled = datetime.fromisoformat(text(publish_at, '发布时间', 64).replace('Z', '+00:00'))
        except ValueError as error:
            raise ProductError('发布时间须使用带时区的日期时间') from error
        if scheduled.utcoffset() is None:
            raise ProductError('发布时间须使用带时区的日期时间')
        source = self.live_content_source(session_id, task_id)
        if source['facts_review'] != 'version_current' or source['segment'] is None:
            raise Conflict('商品事实或片段来源需要重新核对')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM live_content_receipts WHERE session_id=? AND task_id=?',
                          (session_id, task_id)).fetchone():
                raise Conflict('已登记发布结果，不能覆盖原排期')
            result = db.execute("""
                INSERT INTO live_content_schedule
                SELECT session_id, task_id, ?, ?, ?, body FROM live_content_drafts
                WHERE session_id=? AND task_id=? AND withdrawn=0
                ON CONFLICT(session_id, task_id) DO UPDATE SET
                    account=excluded.account, audience=excluded.audience,
                    publish_at=excluded.publish_at, planned_body=excluded.planned_body
            """, (account, audience, scheduled.astimezone(timezone.utc).isoformat(), session_id, task_id))
            if not result.rowcount:
                raise Conflict('请先保存可复用的短视频文案')

    def withdraw_live_content_draft(self, session_id, task_id):
        with self.connect() as db:
            result = db.execute('UPDATE live_content_drafts SET withdrawn=1 WHERE session_id=? AND task_id=?',
                                (session_id, task_id))
            if not result.rowcount:
                raise Conflict('请先保存短视频文案')

    def live_content_draft_withdrawn(self, session_id, task_id):
        with self.connect() as db:
            row = db.execute('SELECT withdrawn FROM live_content_drafts WHERE session_id=? AND task_id=?',
                             (session_id, task_id)).fetchone()
        return bool(row and row['withdrawn'])

    def record_live_content_receipt(self, session_id, task_id, publication_id):
        publication_id = text(publication_id, '平台作品编号', 200)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('''
                SELECT schedule.account, receipt.publication_id, draft.withdrawn,
                       schedule.planned_body=draft.body AS draft_matches
                FROM live_content_schedule schedule
                JOIN live_content_drafts draft USING (session_id, task_id)
                LEFT JOIN live_content_receipts receipt USING (session_id, task_id)
                WHERE session_id=? AND task_id=?
            ''', (session_id, task_id)).fetchone()
            if row is None:
                raise Conflict('请先保存本机排期')
            if row['publication_id'] == publication_id:
                return
            if row['publication_id'] is not None:
                raise Conflict('该排期已登记其他作品编号')
            if row['withdrawn']:
                raise Conflict('草稿已撤回，不能登记新的发布结果')
            if not row['draft_matches']:
                raise Conflict('草稿已修改，请重新保存排期后再登记发布结果')
            result = db.execute('INSERT OR IGNORE INTO live_content_receipts VALUES (?, ?, ?, ?)',
                                (session_id, task_id, row['account'], publication_id))
            if not result.rowcount:
                raise Conflict('该账号的作品编号已关联其他排期')

    def save_live_content_draft(self, session_id, task_id, body):
        body = text(body, '短视频文案', 100000)
        source = self.live_content_source(session_id, task_id)
        if source['facts_review'] != 'version_current' or source['segment'] is None:
            raise Conflict('商品事实或片段来源需要重新核对')
        with self.connect() as db:
            result = db.execute("""
                INSERT INTO live_content_drafts (session_id, task_id, body) VALUES (?, ?, ?)
                ON CONFLICT(session_id, task_id) DO UPDATE SET body=excluded.body
                WHERE live_content_drafts.withdrawn=0
            """, (session_id, task_id, body))
            if not result.rowcount:
                raise Conflict('该文案已停止复用')
        return body

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

    def _after_sales_row(self, product_id, source, period_start, period_end, counts):
        product_id = text(product_id, '商品编号', 64)
        key = self._business_metric_row(product_id, source=source, scope='售后原因',
                                        period_start=period_start, period_end=period_end)[:4]
        categories = {'quality', 'size', 'expectation', 'fulfillment', 'other'}
        if (not isinstance(counts, dict) or not counts or counts.keys() - categories
                or any(type(count) is not int or not 0 <= count < 2**53 for count in counts.values())):
            raise ProductError('售后原因须使用已知分类及非负整数数量')
        return (*key, json.dumps(counts, sort_keys=True))

    def save_after_sales(self, product_id, source, period_start, period_end, counts):
        row = self._after_sales_row(product_id, source, period_start, period_end, counts)
        self._write_after_sales(product_id, [row])

    def _write_after_sales(self, product_id, rows):
        self.get(product_id)
        with self.connect() as db:
            db.executemany("""
                INSERT INTO product_after_sales VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(product_id, source, period_start, period_end) DO UPDATE SET counts=excluded.counts
            """, rows)

    def import_after_sales(self, product_id, content):
        if not isinstance(content, str) or not content.strip():
            raise ProductError('售后 CSV 为空')
        required = {'source', 'period_start', 'period_end'}
        categories = {'quality', 'size', 'expectation', 'fulfillment', 'other'}
        reader = csv.DictReader(io.StringIO(content.lstrip('\ufeff')), strict=True)
        rows = []
        keys = set()
        try:
            names = reader.fieldnames or []
            if (len(names) != len(set(names)) or not required <= set(names)
                    or set(names) - required - categories or not categories.intersection(names)):
                raise ProductError('售后 CSV 表头无效')
            for item in reader:
                try:
                    if None in item or None in item.values():
                        raise ProductError('列数与表头不一致')
                    counts = {}
                    for name in categories.intersection(names):
                        raw = item[name].strip()
                        if raw:
                            if len(raw) > 16 or not raw.isascii() or not raw.isdecimal():
                                raise ProductError(f'{name} 必须是非负整数')
                            counts[name] = int(raw)
                    row = self._after_sales_row(product_id, counts=counts, **{name: item[name] for name in required})
                    if row[:4] in keys:
                        raise ProductError('报表中有重复来源和日期区间')
                    keys.add(row[:4])
                    rows.append(row)
                except ProductError as error:
                    raise ProductError(f'售后 CSV 第 {reader.line_num} 行：{error}') from error
        except csv.Error as error:
            raise ProductError(f'售后 CSV 第 {reader.line_num} 行格式无效') from error
        if not rows:
            raise ProductError('售后 CSV 没有数据行')
        self._write_after_sales(product_id, rows)
        return len(rows)

    def save_after_sales_task(self, product_id, source, period_start, period_end, category, owner, goal):
        if not isinstance(product_id, str) or not 1 <= len(product_id) <= 64:
            raise ProductError('商品编号无效')
        owner = text(owner, '负责人', 120)
        goal = text(goal, '改进目标', 2000)
        category = text(category, '售后原因', 32)
        key = self._business_metric_row(product_id, source=source, period_start=period_start,
                                        period_end=period_end, scope='售后原因')[:4]
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            report = db.execute("""
                SELECT counts FROM product_after_sales
                WHERE product_id=? AND source=? AND period_start=? AND period_end=?
            """, key).fetchone()
            count = json.loads(report['counts']).get(category, 0) if report else 0
            if not count:
                raise Conflict('当前报表没有该售后原因的记录')
            db.execute("""
                INSERT INTO product_after_sales_tasks
                    (product_id, source, period_start, period_end, category, evidence_count, owner, goal)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(product_id, source, period_start, period_end, category) DO UPDATE SET
                    evidence_count=excluded.evidence_count, owner=excluded.owner, goal=excluded.goal, revoked=0
            """, (*key, category, count, owner, goal))

    def revoke_after_sales_task(self, product_id, source, period_start, period_end, category):
        with self.connect() as db:
            result = db.execute("""
                UPDATE product_after_sales_tasks SET revoked=1
                WHERE product_id=? AND source=? AND period_start=? AND period_end=? AND category=?
            """, (product_id, source, period_start, period_end, category))
            if not result.rowcount:
                raise Conflict('未找到对应售后任务')

    def after_sales_tasks(self, product_ids, *, current_only=False):
        if not product_ids:
            return []
        placeholders = ', '.join('?' for _ in product_ids)
        with self.connect() as db:
            rows = db.execute(f"""
                SELECT task.*, report.counts AS current_counts
                FROM product_after_sales_tasks task LEFT JOIN product_after_sales report
                USING (product_id, source, period_start, period_end)
                WHERE task.product_id IN ({placeholders})
                ORDER BY task.product_id, task.period_end DESC, task.source, task.category
            """, product_ids).fetchall()
        tasks = []
        for row in rows:
            task = dict(row)
            current_counts = json.loads(task.pop('current_counts') or '{}')
            task['revoked'] = bool(task['revoked'])
            if not current_only or (not task['revoked'] and current_counts.get(task['category']) == task['evidence_count']):
                tasks.append(task)
        return tasks

    def compare_after_sales(self, product_id, source, baseline_start, baseline_end, trial_start, trial_end):
        baseline = self._business_metric_row(product_id, source=source, period_start=baseline_start,
                                             period_end=baseline_end, scope='售后原因')[:4]
        trial = self._business_metric_row(product_id, source=source, period_start=trial_start,
                                          period_end=trial_end, scope='售后原因')[:4]
        if baseline_end >= trial_start:
            raise ProductError('基线窗口须早于试验窗口，且两者不能重叠')
        with self.connect() as db:
            db.execute('BEGIN')
            counts = []
            for key in (baseline, trial):
                row = db.execute("""
                    SELECT counts FROM product_after_sales
                    WHERE product_id=? AND source=? AND period_start=? AND period_end=?
                """, key).fetchone()
                if not row:
                    raise ProductError('缺少与所选窗口完全对应的售后报表')
                counts.append(json.loads(row['counts']))
        categories = ('quality', 'size', 'expectation', 'fulfillment', 'other')
        return {
            'product_id': product_id, 'source': baseline[1],
            'baseline': {'period_start': baseline_start, 'period_end': baseline_end, 'counts': counts[0]},
            'trial': {'period_start': trial_start, 'period_end': trial_end, 'counts': counts[1]},
            'differences': {name: counts[1][name] - counts[0][name] if all(name in row for row in counts) else None
                            for name in categories},
            'conclusion': 'uncertain',
        }

    def after_sales(self, product_id):
        self.get(product_id)
        tasks = {(item['source'], item['period_start'], item['period_end'], item['category']): item
                 for item in self.after_sales_tasks([product_id])}
        with self.connect() as db:
            rows = db.execute('SELECT * FROM product_after_sales WHERE product_id=? ORDER BY period_end DESC, source',
                              (product_id,)).fetchall()
        recommendations = {
            'quality': '抽样核对质量问题，确认需要补充的实拍或检查说明',
            'size': '核对规格和测量方法，必要时补充尺寸 FAQ',
            'expectation': '核对买家预期与商品事实，检查卖点和演示是否需要改写',
            'fulfillment': '核对发货条件及承诺，必要时更新口播和导购说明',
            'other': '抽样核对其他原因，再确定要修改的资料',
        }
        reports = []
        for row in rows:
            counts = json.loads(row['counts'])
            followups = [{'category': category, 'count': count, 'recommendation': recommendations[category]}
                         for category, count in counts.items() if count > 0]
            for followup in followups:
                task = tasks.get((row['source'], row['period_start'], row['period_end'], followup['category']))
                if task:
                    followup['task'] = task
            reports.append({**dict(row), 'counts': counts, 'followups': followups})
        return reports

    def save_sourcing_candidate(self, name, supplier, source, observed_on, details):
        name = text(name, '候选商品', 120)
        supplier = text(supplier, '供应商', 120)
        source = text(source, '资料来源', 500)
        if not isinstance(observed_on, str):
            raise ProductError('请填写资料日期')
        try:
            if date.fromisoformat(observed_on).isoformat() != observed_on:
                raise ValueError
        except ValueError as error:
            raise ProductError('资料日期须为 YYYY-MM-DD') from error
        fields = {'access', 'demand', 'competition', 'terms', 'minimum_order', 'lead_time', 'logistics', 'quality_evidence'}
        if not isinstance(details, dict) or details.keys() - fields:
            raise ProductError('采购资料字段无效')
        details = {key: text(value, '采购资料', 2000) for key, value in details.items()}
        candidate_id = str(uuid.uuid4())
        with self.connect() as db:
            db.execute('INSERT INTO sourcing_candidates VALUES (?, ?, ?, ?, ?, ?)',
                       (candidate_id, name, supplier, source, observed_on, json.dumps(details, ensure_ascii=False)))
        return candidate_id

    def sourcing_candidates(self):
        with self.connect() as db:
            rows = db.execute('SELECT * FROM sourcing_candidates ORDER BY observed_on DESC, rowid DESC').fetchall()
        return [{**dict(row), 'details': json.loads(row['details'])} for row in rows]

    def save_sourcing_trial(self, candidate_id, sample_evidence, trial_evidence, cost_minor, verdict, metrics=None):
        sample_evidence = text(sample_evidence, '样品核验依据', 2000)
        trial_evidence = text(trial_evidence, '试卖记录或待办', 2000)
        if cost_minor is not None and (type(cost_minor) is not int or not 0 <= cost_minor < 2**53):
            raise ProductError('样品成本须为非负整数分或未知')
        if verdict not in ('pending', 'pass', 'fail'):
            raise ProductError('样品核验结果无效')
        if metrics is not None:
            if (not isinstance(metrics, dict) or metrics.keys() - {'orders', 'refunds', 'fulfilled_on_time', 'gross_profit_minor'}
                    or any(type(amount) is not int or abs(amount) >= 2**53
                           or (key != 'gross_profit_minor' and amount < 0) for key, amount in metrics.items())):
                raise ProductError('试卖数量须为非负整数，毛利须为整数分，均可留空')
            if 'orders' in metrics and any(metrics.get(key, 0) > metrics['orders']
                                          for key in ('refunds', 'fulfilled_on_time')):
                raise ProductError('同批试卖的退款或按时履约数量不能超过订单数量')
        with self.connect() as db:
            result = db.execute("""
                INSERT INTO sourcing_trials (candidate_id, sample_evidence, trial_evidence, cost_minor, verdict, metrics)
                SELECT id, ?, ?, ?, ?, ? FROM sourcing_candidates WHERE id=?
                ON CONFLICT(candidate_id) DO UPDATE SET sample_evidence=excluded.sample_evidence,
                    trial_evidence=excluded.trial_evidence, cost_minor=excluded.cost_minor, verdict=excluded.verdict,
                    metrics=excluded.metrics
            """, (sample_evidence, trial_evidence, cost_minor, verdict, json.dumps(metrics) if metrics is not None else None,
                  candidate_id))
            if not result.rowcount:
                raise ProductError('采购候选不存在')

    def sourcing_trial(self, candidate_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM sourcing_trials WHERE candidate_id=?', (candidate_id,)).fetchone()
        return self._decode_sourcing_trial(row)

    @staticmethod
    def _decode_sourcing_trial(row):
        if row is None:
            return None
        trial = dict(row)
        metrics = trial.pop('metrics')
        if metrics is not None:
            trial['metrics'] = json.loads(metrics)
        return trial

    def save_sourcing_decision(self, candidate_id, decision, rationale, constraints):
        if decision not in ('adopt', 'continue', 'drop'):
            raise ProductError('采购辅助结论无效')
        rationale = text(rationale, '结论依据', 2000)
        constraints = text(constraints, '资金及库存约束', 2000)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            candidate = db.execute('SELECT id FROM sourcing_candidates WHERE id=?', (candidate_id,)).fetchone()
            if not candidate:
                raise ProductError('采购候选不存在')
            trial = db.execute('SELECT * FROM sourcing_trials WHERE candidate_id=?', (candidate_id,)).fetchone()
            if decision == 'adopt' and (not trial or trial['verdict'] != 'pass' or trial['cost_minor'] is None):
                raise Conflict('采用前需要商家核验通过的样品及已知样品成本')
            snapshot = {'candidate_id': candidate_id, 'decision': decision, 'rationale': rationale,
                        'constraints': constraints, 'trial': self._decode_sourcing_trial(trial),
                        'recorded_at': datetime.now(timezone.utc).isoformat()}
            db.execute('INSERT OR REPLACE INTO sourcing_decisions VALUES (?, ?)',
                       (candidate_id, json.dumps(snapshot, ensure_ascii=False)))
        return snapshot

    def sourcing_decision(self, candidate_id):
        with self.connect() as db:
            row = db.execute('SELECT snapshot FROM sourcing_decisions WHERE candidate_id=?', (candidate_id,)).fetchone()
        return json.loads(row['snapshot']) if row else None

    def save_promotion_spend(self, product_id, source, period_start, period_end, campaign, asset,
                             spend_minor, attribution=None):
        if not isinstance(product_id, str) or not 1 <= len(product_id) <= 64:
            raise ProductError('商品编号无效')
        key = self._business_metric_row(product_id, source=source, period_start=period_start,
                                        period_end=period_end, scope='投放费用')[:4]
        campaign = text(campaign, '活动编号', 120)
        asset = text(asset, '素材编号', 120)
        if type(spend_minor) is not int or not 0 <= spend_minor < 2**53:
            raise ProductError('支出须为非负整数分')
        if attribution is not None:
            attribution = text(attribution, '归因口径', 500)
        self.get(product_id)
        with self.connect() as db:
            db.execute("""
                INSERT INTO promotion_spend VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(product_id, source, period_start, period_end, campaign, asset)
                DO UPDATE SET spend_minor=excluded.spend_minor, attribution=excluded.attribution
            """, (*key, campaign, asset, spend_minor, attribution))

    def save_promotion_plan(self, product_id, source, period_start, period_end, campaign, asset, budget_minor, rationale):
        rationale = text(rationale, '调整理由', 2000)
        if type(budget_minor) is not int or not 0 <= budget_minor < 2**53:
            raise ProductError('预算上限须为非负整数分')
        keys = (product_id, source, period_start, period_end, campaign, asset)
        if any(not isinstance(value, str) or not value.strip() for value in keys):
            raise ProductError('投放方案需要完整的账单定位条件')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            bill = db.execute("""
                SELECT * FROM promotion_spend WHERE product_id=? AND source=? AND period_start=?
                    AND period_end=? AND campaign=? AND asset=?
            """, keys).fetchone()
            if not bill:
                raise ProductError('缺少对应的投放账单')
            if bill['spend_minor'] > budget_minor:
                raise Conflict('账单支出已超过预算上限')
            snapshot = {'id': str(uuid.uuid4()), 'bill': dict(bill), 'budget_minor': budget_minor,
                        'rationale': rationale, 'recorded_at': datetime.now(timezone.utc).isoformat()}
            db.execute('INSERT INTO promotion_plans VALUES (?, ?, ?)',
                       (snapshot['id'], product_id, json.dumps(snapshot, ensure_ascii=False)))
        return snapshot

    def promotion_plans(self, product_id):
        keys = ('source', 'period_start', 'period_end', 'campaign', 'asset')
        bills = {tuple(bill[key] for key in keys): bill for bill in self.promotion_spend(product_id)}
        with self.connect() as db:
            rows = db.execute('''SELECT snapshot, COALESCE((
                SELECT action FROM promotion_plan_actions WHERE plan_id=promotion_plans.id ORDER BY rowid DESC LIMIT 1
            ), 'draft') AS status FROM promotion_plans WHERE product_id=? ORDER BY rowid DESC''',
                              (product_id,)).fetchall()
        plans = []
        for row in rows:
            plan = json.loads(row['snapshot'])
            bill = plan['bill']
            current = bills.get(tuple(bill[key] for key in keys))
            plan['status'] = 'stale' if row['status'] == 'approved' and current != bill else row['status']
            plans.append(plan)
        return plans

    def update_promotion_plan(self, plan_id, action):
        if action not in ('approved', 'paused'):
            raise ProductError('投放方案操作无效')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT snapshot FROM promotion_plans WHERE id=?', (plan_id,)).fetchone()
            if not row:
                raise ProductError('投放方案不存在')
            snapshot = json.loads(row['snapshot'])
            if action == 'approved':
                bill = snapshot['bill']
                keys = ('product_id', 'source', 'period_start', 'period_end', 'campaign', 'asset')
                current = db.execute("""
                    SELECT * FROM promotion_spend WHERE product_id=? AND source=? AND period_start=?
                        AND period_end=? AND campaign=? AND asset=?
                """, tuple(bill[key] for key in keys)).fetchone()
                if current is None or dict(current) != bill:
                    raise Conflict('账单已变化，请重新核对并保存方案')
            previous = db.execute('SELECT action FROM promotion_plan_actions WHERE plan_id=? ORDER BY rowid DESC LIMIT 1',
                                  (plan_id,)).fetchone()
            if previous is None or previous['action'] != action:
                db.execute('INSERT INTO promotion_plan_actions VALUES (?, ?, ?)',
                           (plan_id, action, datetime.now(timezone.utc).isoformat()))
        return {**snapshot, 'status': action}

    def promotion_plan_actions(self, plan_id):
        with self.connect() as db:
            if not db.execute('SELECT 1 FROM promotion_plans WHERE id=?', (plan_id,)).fetchone():
                raise ProductError('投放方案不存在')
            rows = db.execute('SELECT action, occurred_at FROM promotion_plan_actions WHERE plan_id=? ORDER BY rowid',
                              (plan_id,)).fetchall()
        return [dict(row) for row in rows]

    def promotion_spend(self, product_id):
        self.get(product_id)
        with self.connect() as db:
            rows = db.execute("""
                SELECT * FROM promotion_spend WHERE product_id=?
                ORDER BY period_end DESC, source, campaign, asset
            """, (product_id,)).fetchall()
        return [dict(row) for row in rows]

    def compare_promotion_spend(self, product_id, source, campaign, asset,
                                baseline_start, baseline_end, trial_start, trial_end):
        windows = ((baseline_start, baseline_end), (trial_start, trial_end))
        keys = [self._business_metric_row(product_id, source=source, period_start=start,
                                          period_end=end, scope='投放费用')[:4]
                for start, end in windows]
        if baseline_end >= trial_start:
            raise ProductError('基线窗口须早于试验窗口且不能重叠')
        with self.connect() as db:
            db.execute('BEGIN')
            bills = []
            for key in keys:
                row = db.execute("""
                    SELECT * FROM promotion_spend WHERE product_id=? AND source=? AND period_start=?
                        AND period_end=? AND campaign=? AND asset=?
                """, (*key, campaign, asset)).fetchone()
                if row is None:
                    raise ProductError('缺少相同活动和素材的对应账单')
                bills.append(dict(row))
        return {'baseline': bills[0], 'trial': bills[1],
                'spend_difference_minor': bills[1]['spend_minor'] - bills[0]['spend_minor'],
                'conclusion': 'uncertain', 'missing': ['attributed_orders', 'attributed_refunds', 'net_result']}

    def compare_product_facts(self, product_ids, fact_names):
        now = datetime.now(timezone.utc)
        items = []
        for product_id in product_ids:
            product = self.get(product_id)
            facts = verified_product_facts(product, now=now)
            items.append({
                'product_id': product_id, 'product_version': product['version'], 'title': product['title'],
                'facts': {name: {'value': facts[name]['value'], 'source': facts[name]['source']}
                          if name in facts else None for name in fact_names},
            })
        return items

    def product_selection_evidence(self):
        fields = ('适播性', '目标人群', '售价', '成本', '库存', '发货条件', '排品角色')
        now = datetime.now(timezone.utc)
        result = []
        for product in self.list():
            facts = verified_product_facts(product, now=now)
            stock = facts.get('库存', {}).get('value')
            suitability = facts.get('适播性', {}).get('value')
            if type(stock) is int and stock == 0:
                role, reason = 'hold', '已核对库存为零'
            elif suitability == '不适播':
                role, reason = 'hold', '已核对为不适播'
            elif type(stock) is not int or stock < 0 or '发货条件' not in facts:
                role, reason = 'hold', '需核对可售库存和发货条件'
            elif suitability == '适播' and '目标人群' in facts:
                if facts.get('排品角色', {}).get('value') == '主推' and {'售价', '成本'} <= facts.keys():
                    role, reason = 'primary', '商家已核对主推角色，适播、人群、库存、发货、售价与成本依据齐备'
                else:
                    role, reason = 'support', '已有适播、人群、库存及发货依据，可作为辅助商品'
            else:
                role, reason = 'trial', '库存与发货条件已核对，可小范围试播'
            result.append({
                'product_id': product['id'], 'product_version': product['version'], 'title': product['title'],
                'conditions': {name: {'value': facts[name]['value'], 'source': facts[name]['source']}
                               if name in facts else None for name in fields},
                'verified_fact_count': len(facts),
                'recommendation': {'role': role, 'reason': reason},
            })
        return result

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
