# -*- coding: utf-8 -*-
"""
用户管理 + 音色数据库层
SQLite, 零依赖
"""
import sqlite3
import hashlib
import os
import time

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'p2v.db')


def _get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """建表（幂等）"""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT DEFAULT '',
            created_at REAL DEFAULT (strftime('%s','now'))
        );
        CREATE TABLE IF NOT EXISTS user_voices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            voice_name TEXT NOT NULL,
            cosyvoice_speaker_id TEXT UNIQUE NOT NULL,
            prompt_text TEXT DEFAULT '',
            created_at REAL DEFAULT (strftime('%s','now')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
    """)
    conn.commit()
    conn.close()


def _hash_pw(password: str) -> str:
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


# ─── 用户操作 ───

def create_user(username: str, password: str, display_name: str = "") -> dict:
    """注册用户, 返回 user dict 或 raise"""
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, display_name) VALUES (?,?,?)",
            (username.strip(), _hash_pw(password), display_name or username)
        )
        conn.commit()
        user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        return dict(user)
    except sqlite3.IntegrityError:
        raise ValueError(f"用户名 '{username}' 已存在")
    finally:
        conn.close()


def verify_user(username: str, password: str) -> dict | None:
    """验证密码, 成功返回 user dict, 失败返回 None"""
    conn = _get_conn()
    user = conn.execute(
        "SELECT * FROM users WHERE username=? AND password_hash=?",
        (username.strip(), _hash_pw(password))
    ).fetchone()
    conn.close()
    return dict(user) if user else None


def get_user_by_id(user_id: int) -> dict | None:
    conn = _get_conn()
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return dict(user) if user else None


# ─── 音色操作 ───

def make_speaker_id(user_id: int, voice_name: str) -> str:
    """生成唯一的 CosyVoice speaker_id: u{user_id}_{hash}"""
    h = hashlib.md5(voice_name.encode()).hexdigest()[:8]
    return f"u{user_id}_{h}"


def add_voice(user_id: int, voice_name: str, cosyvoice_speaker_id: str, prompt_text: str = "") -> dict:
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO user_voices (user_id, voice_name, cosyvoice_speaker_id, prompt_text) VALUES (?,?,?,?)",
            (user_id, voice_name, cosyvoice_speaker_id, prompt_text)
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM user_voices WHERE cosyvoice_speaker_id=?", (cosyvoice_speaker_id,)
        ).fetchone()
        return dict(row)
    except sqlite3.IntegrityError:
        raise ValueError(f"音色名 '{voice_name}' 已存在")
    finally:
        conn.close()


def get_user_voices(user_id: int) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM user_voices WHERE user_id=? ORDER BY created_at DESC", (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_voice(user_id: int, voice_id: int) -> str | None:
    """删除音色, 返回被删除的 cosyvoice_speaker_id (用于调 CosyVoice API 清理)"""
    conn = _get_conn()
    row = conn.execute(
        "SELECT cosyvoice_speaker_id FROM user_voices WHERE id=? AND user_id=?",
        (voice_id, user_id)
    ).fetchone()
    if not row:
        conn.close()
        return None
    speaker_id = row['cosyvoice_speaker_id']
    conn.execute("DELETE FROM user_voices WHERE id=? AND user_id=?", (voice_id, user_id))
    conn.commit()
    conn.close()
    return speaker_id


def get_voice_by_speaker_id(user_id: int, cosyvoice_speaker_id: str) -> dict | None:
    """验证某个 speaker_id 确实属于该用户"""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM user_voices WHERE user_id=? AND cosyvoice_speaker_id=?",
        (user_id, cosyvoice_speaker_id)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# 启动时自动建表
init_db()
