import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'automation.db')


def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = get_db()
    cursor = db.cursor()
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            genre TEXT NOT NULL,
            youtube_channel_id TEXT,
            youtube_channel_name TEXT,
            oauth_token_path TEXT,
            video_length INTEGER DEFAULT 12,
            video_length_min INTEGER DEFAULT 10,
            video_length_max INTEGER DEFAULT 15,
            videos_per_day INTEGER DEFAULT 1,
            shorts_per_day INTEGER DEFAULT 2,
            upload_frequency TEXT DEFAULT 'once_daily',
            active INTEGER DEFAULT 1,
            subscriber_count INTEGER DEFAULT 0,
            view_count INTEGER DEFAULT 0,
            last_upload TEXT,
            status TEXT DEFAULT 'not_connected',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id INTEGER,
            title TEXT,
            description TEXT,
            local_path TEXT,
            youtube_video_id TEXT,
            duration INTEGER,
            video_type TEXT DEFAULT 'long_form',
            status TEXT DEFAULT 'pending',
            scheduled_time TEXT,
            uploaded_at TEXT,
            views INTEGER DEFAULT 0,
            error_message TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(channel_id) REFERENCES channels(id)
        );

        CREATE TABLE IF NOT EXISTS stock_videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            source_id TEXT UNIQUE,
            url TEXT,
            local_path TEXT,
            genre TEXT,
            duration INTEGER,
            downloaded_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT,
            title TEXT,
            message TEXT,
            channel_id INTEGER,
            read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id INTEGER,
            subscriber_count INTEGER,
            view_count INTEGER,
            estimated_earnings REAL,
            recorded_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(channel_id) REFERENCES channels(id)
        );

        CREATE TABLE IF NOT EXISTS upload_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id INTEGER,
            video_id INTEGER,
            title TEXT,
            duration INTEGER,
            status TEXT,
            youtube_video_id TEXT,
            views INTEGER DEFAULT 0,
            uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(channel_id) REFERENCES channels(id)
        );

        CREATE TABLE IF NOT EXISTS tts_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            month_key TEXT NOT NULL,
            chars_used INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Add new columns to existing channels table if they don't exist
    try:
        cursor.execute("ALTER TABLE channels ADD COLUMN video_length_min INTEGER DEFAULT 10")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE channels ADD COLUMN video_length_max INTEGER DEFAULT 15")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE channels ADD COLUMN videos_per_day INTEGER DEFAULT 1")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE channels ADD COLUMN shorts_per_day INTEGER DEFAULT 2")
    except Exception:
        pass

    db.commit()
    db.close()
    print("Database initialized.")
