"""Shared, fact-free preparation templates for managed shop workspaces."""
import json
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import uuid

from scripts.product_store import ProductError


def _text(value, label, maximum):
    if not isinstance(value, str) or len(value) > maximum:
        raise ProductError(f'{label}必须是 {maximum} 字以内的文本')
    return value.strip()


class PreparationTemplateStore:
    """Stores reusable structure without product, promotion, stock, shipping or account data."""
    def __init__(self, directory):
        self.path = Path(directory) / 'shared-preparation-templates.sqlite3'

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def _value(row):
        return {'id': row['id'], 'name': row['name'], **json.loads(row['body']),
                'created_at': row['created_at']}

    def save(self, *, name, goal, audience, constraints):
        name = _text(name, '模板名称', 100)
        labels = {'goal': '场次目标', 'audience': '目标人群', 'constraints': '本场限制'}
        body = {field: _text(value, labels[field], 2000) for field, value in {
            'goal': goal, 'audience': audience, 'constraints': constraints,
        }.items()}
        if not name:
            raise ProductError('请填写模板名称')
        if not any(body.values()):
            raise ProductError('模板至少需要填写场次目标、目标人群或本场限制')
        value = {'id': uuid.uuid4().hex, 'name': name, **body,
                 'created_at': datetime.now(timezone.utc).isoformat()}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS preparation_templates (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, body TEXT NOT NULL,
                created_at TEXT NOT NULL)''')
            db.execute('INSERT INTO preparation_templates VALUES (?, ?, ?, ?)',
                       (value['id'], name, json.dumps(body, ensure_ascii=False), value['created_at']))
            db.commit()
        return value

    def list(self):
        if not self.path.is_file():
            return []
        with self.connect() as db:
            rows = db.execute('SELECT * FROM preparation_templates ORDER BY created_at, id').fetchall()
        return [self._value(row) for row in rows]

    def get(self, identifier):
        if (not isinstance(identifier, str) or len(identifier) != 32
                or any(character not in '0123456789abcdef' for character in identifier)):
            raise ProductError('请选择有效准备模板')
        if not self.path.is_file():
            raise ProductError('准备模板不存在')
        with self.connect() as db:
            row = db.execute('SELECT * FROM preparation_templates WHERE id=?', (identifier,)).fetchone()
        if row is None:
            raise ProductError('准备模板不存在')
        return self._value(row)
