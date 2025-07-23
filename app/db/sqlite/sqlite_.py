"""app/db/sqlite/sqlite_.py (修复和优化版)"""

import sqlite3
import uuid
import os
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
import threading
import logging

# --- 最佳实践建议 ---
# 更新 'updated_at' 时间戳的责任已从数据库触发器移至应用程序层。
# 这可以避免递归触发器错误，使代码更明确，更易于调试。
#
# 当您更新 'user' 或 'room' 表中的记录时，您必须手动将 'updated_at' 字段设置为当前的 Unix 时间戳。
# 示例:
#   current_timestamp = int(datetime.utcnow().timestamp())
#   db.execute("UPDATE user SET name = ?, updated_at = ? WHERE user_uuid = ?",
#              ('new_name', current_timestamp, 'some_uuid'))
# ------------------------------------

class SQLiteDB:
    """
    一个用于管理SQLite数据库的类，经过优化和修复。
    支持多线程环境，使用线程本地存储来管理连接。
    """
    def __init__(self, db_path: str = "chat.db"):
        """
        初始化SQLite数据库连接。

        Args:
            db_path (str): 数据库文件路径。
        """
        self.db_path = db_path
        # 使用线程本地存储，确保每个线程拥有一个独立的连接
        self._local = threading.local()
        self.init_database()
        logging.info(f"数据库已初始化于 {os.path.abspath(self.db_path)}")

    def init_database(self):
        """
        初始化数据库，创建表结构和索引。
        如果表已存在，则不会重复创建。
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 启用外键支持
            cursor.execute('PRAGMA foreign_keys = ON')
            # 设置 WAL 模式以提高并发性
            cursor.execute('PRAGMA journal_mode = WAL')
            # 优化同步模式以平衡性能和安全性
            cursor.execute('PRAGMA synchronous = NORMAL')
            # 设置更大的缓存大小（例如 64MB）
            cursor.execute('PRAGMA cache_size = -64000')

            # --- 表定义 ---
            # 注意: 所有 DATETIME 字段已替换为 INTEGER 以存储 Unix 时间戳。
            # 这对于排序和范围查询更高效。
            # 默认值现在是当前的 Unix 时间戳。

            # `user` 表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user (
                    user_uuid TEXT PRIMARY KEY,
                    qq_number TEXT UNIQUE,
                    name TEXT NOT NULL,
                    avatar_path TEXT,
                    role TEXT DEFAULT 'user' CHECK (role IN ('admin', 'super_admin', 'user')),
                    password_hash TEXT,
                    inviter TEXT,
                    is_active INTEGER DEFAULT 1,
                    last_login_at INTEGER,
                    created_at INTEGER DEFAULT (strftime('%s', 'now')),
                    updated_at INTEGER DEFAULT (strftime('%s', 'now')),
                    FOREIGN KEY (inviter) REFERENCES user(user_uuid) ON DELETE SET NULL
                )
            ''')

            # `room` 表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS room (
                    room_uuid TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    avatar_path TEXT,
                    max_online_users INTEGER DEFAULT 100 CHECK (max_online_users > 0),
                    max_join_users INTEGER DEFAULT 500 CHECK (max_join_users > 0),
                    is_active INTEGER DEFAULT 1,
                    created_at INTEGER DEFAULT (strftime('%s', 'now')),
                    updated_at INTEGER DEFAULT (strftime('%s', 'now')),
                    creator TEXT NOT NULL,
                    FOREIGN KEY (creator) REFERENCES user(user_uuid) ON DELETE CASCADE
                )
            ''')

            # `message` 表（用于群聊/房间聊天）
            # 消息通常不可变，因此不需要 `updated_at`。
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS message (
                    msg_uuid TEXT PRIMARY KEY,
                    sender TEXT NOT NULL,
                    msg_type TEXT DEFAULT 'text' CHECK (msg_type IN ('text', 'image', 'audio', 'video', 'system', 'file')),
                    content TEXT NOT NULL,
                    room_uuid TEXT NOT NULL,
                    reply_to TEXT,
                    file_path TEXT,
                    file_size INTEGER,
                    is_deleted INTEGER DEFAULT 0,
                    created_at INTEGER DEFAULT (strftime('%s', 'now')),
                    FOREIGN KEY (sender) REFERENCES user(user_uuid) ON DELETE CASCADE,
                    FOREIGN KEY (room_uuid) REFERENCES room(room_uuid) ON DELETE CASCADE,
                    FOREIGN KEY (reply_to) REFERENCES message(msg_uuid) ON DELETE SET NULL
                )
            ''')

            # `private_message` 表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS private_message (
                    msg_uuid TEXT PRIMARY KEY,
                    sender_uuid TEXT NOT NULL,
                    receiver_uuid TEXT NOT NULL,
                    msg_type TEXT DEFAULT 'text' CHECK (msg_type IN ('text', 'image', 'audio', 'video', 'system', 'file')),
                    content TEXT NOT NULL,
                    reply_to TEXT,
                    file_path TEXT,
                    file_size INTEGER,
                    is_deleted INTEGER DEFAULT 0,
                    is_read INTEGER DEFAULT 0,
                    created_at INTEGER DEFAULT (strftime('%s', 'now')),
                    FOREIGN KEY (sender_uuid) REFERENCES user(user_uuid) ON DELETE CASCADE,
                    FOREIGN KEY (receiver_uuid) REFERENCES user(user_uuid) ON DELETE CASCADE,
                    FOREIGN KEY (reply_to) REFERENCES private_message(msg_uuid) ON DELETE SET NULL
                )
            ''')

            # `user_room` 连接表（多对多关系）
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_room (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_uuid TEXT NOT NULL,
                    room_uuid TEXT NOT NULL,
                    role TEXT DEFAULT 'member' CHECK (role IN ('owner', 'admin', 'member')),
                    is_muted INTEGER DEFAULT 0,
                    joined_at INTEGER DEFAULT (strftime('%s', 'now')),
                    left_at INTEGER,
                    FOREIGN KEY (user_uuid) REFERENCES user(user_uuid) ON DELETE CASCADE,
                    FOREIGN KEY (room_uuid) REFERENCES room(room_uuid) ON DELETE CASCADE,
                    UNIQUE(user_uuid, room_uuid)
                )
            ''')

            # `message_read_status` 表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS message_read_status (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_uuid TEXT NOT NULL,
                    message_uuid TEXT NOT NULL,
                    room_uuid TEXT NOT NULL,
                    read_at INTEGER DEFAULT (strftime('%s', 'now')),
                    FOREIGN KEY (user_uuid) REFERENCES user(user_uuid) ON DELETE CASCADE,
                    FOREIGN KEY (message_uuid) REFERENCES message(msg_uuid) ON DELETE CASCADE,
                    FOREIGN KEY (room_uuid) REFERENCES room(room_uuid) ON DELETE CASCADE,
                    UNIQUE(user_uuid, message_uuid)
                )
            ''')

            # 创建索引以提升性能
            self._create_indexes(cursor)

            conn.commit()

    def _create_indexes(self, cursor):
        """创建索引以提高查询性能"""
        indexes = [
            # user 表索引
            'CREATE INDEX IF NOT EXISTS idx_user_qq_number ON user(qq_number)',
            'CREATE INDEX IF NOT EXISTS idx_user_role ON user(role)',
            'CREATE INDEX IF NOT EXISTS idx_user_is_active ON user(is_active)',
            'CREATE INDEX IF NOT EXISTS idx_user_created_at ON user(created_at)',

            # room 表索引
            'CREATE INDEX IF NOT EXISTS idx_room_creator ON room(creator)',
            'CREATE INDEX IF NOT EXISTS idx_room_is_active ON room(is_active)',
            'CREATE INDEX IF NOT EXISTS idx_room_created_at ON room(created_at)',

            # message 表索引
            'CREATE INDEX IF NOT EXISTS idx_message_sender ON message(sender)',
            'CREATE INDEX IF NOT EXISTS idx_message_room_uuid ON message(room_uuid)',
            'CREATE INDEX IF NOT EXISTS idx_message_created_at ON message(created_at)',
            'CREATE INDEX IF NOT EXISTS idx_message_msg_type ON message(msg_type)',
            'CREATE INDEX IF NOT EXISTS idx_message_is_deleted ON message(is_deleted)',
            'CREATE INDEX IF NOT EXISTS idx_message_reply_to ON message(reply_to)',
            'CREATE INDEX IF NOT EXISTS idx_message_room_time ON message(room_uuid, created_at DESC)',
            'CREATE INDEX IF NOT EXISTS idx_message_room_active ON message(room_uuid, is_deleted, created_at DESC)',

            # private_message 表索引
            'CREATE INDEX IF NOT EXISTS idx_pm_sender ON private_message(sender_uuid)',
            'CREATE INDEX IF NOT EXISTS idx_pm_receiver ON private_message(receiver_uuid)',
            'CREATE INDEX IF NOT EXISTS idx_pm_created_at ON private_message(created_at)',
            'CREATE INDEX IF NOT EXISTS idx_pm_is_read ON private_message(is_read)',
            'CREATE INDEX IF NOT EXISTS idx_pm_conversation ON private_message(sender_uuid, receiver_uuid, created_at DESC)',

            # user_room 表索引
            'CREATE INDEX IF NOT EXISTS idx_user_room_user ON user_room(user_uuid)',
            'CREATE INDEX IF NOT EXISTS idx_user_room_room ON user_room(room_uuid)',
            'CREATE INDEX IF NOT EXISTS idx_user_room_joined_at ON user_room(joined_at)',
            'CREATE INDEX IF NOT EXISTS idx_user_room_left_at ON user_room(left_at)',

            # message_read_status 表索引
            'CREATE INDEX IF NOT EXISTS idx_read_status_user ON message_read_status(user_uuid)',
            'CREATE INDEX IF NOT EXISTS idx_read_status_room ON message_read_status(room_uuid)',
            'CREATE INDEX IF NOT EXISTS idx_read_status_message ON message_read_status(message_uuid)',
        ]

        for index_sql in indexes:
            cursor.execute(index_sql)

    @contextmanager
    def get_connection(self):
        """
        获取数据库连接的上下文管理器。
        它为每个线程维护一个独立的连接，以确保线程安全。
        """
        # 检查当前线程是否已存在连接
        if not hasattr(self._local, 'connection'):
            try:
                # 如果不存在，为该线程创建一个新连接
                self._local.connection = sqlite3.connect(
                    self.db_path,
                    check_same_thread=False, # 线程本地使用所需
                    timeout=30.0
                )
                # 使用 sqlite3.Row 作为行工厂，以获取类似字典的行
                self._local.connection.row_factory = sqlite3.Row
                self._local.connection.execute('PRAGMA foreign_keys = ON')
            except sqlite3.Error as e:
                logging.error(f"连接数据库失败: {e}")
                raise

        try:
            yield self._local.connection
        except Exception as e:
            # 在事务期间发生任何异常时回滚
            self._local.connection.rollback()
            logging.error(f"数据库操作失败，事务已回滚: {e}")
            raise
        finally:
            # 此处故意不关闭连接。
            # 它保持打开状态，以便在同一线程内重用以提高性能。
            # 应用程序负责在线程结束时调用 close_connection()。
            pass

    def close_connection(self):
        """
        关闭当前线程的数据库连接。
        **重要**: 应用程序必须在线程结束时或应用关闭时调用此方法，以防止连接泄漏。
        """
        if hasattr(self._local, 'connection'):
            self._local.connection.close()
            delattr(self._local, 'connection')
            logging.info("已为当前线程关闭数据库连接。")

    def execute_transaction(self, operations: List[tuple]):
        """
        在单个事务中执行多个SQL操作。

        Args:
            operations (List[tuple]): 一个操作列表，每个元素是一个 (sql, params) 的元组。

        Returns:
            bool: 成功返回 True，失败返回 False。
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                for sql, params in operations:
                    cursor.execute(sql, params or ())
                conn.commit()
                return True
            except sqlite3.Error as e:
                conn.rollback()
                logging.error(f"事务失败: {e}")
                return False

    def vacuum_database(self):
        """清理数据库，重建并回收未使用的空间。"""
        with self.get_connection() as conn:
            logging.info("开始数据库 VACUUM...")
            conn.execute('VACUUM')
            logging.info("数据库 VACUUM 完成。")

    def analyze_database(self):
        """分析数据库，更新统计信息以帮助查询规划器优化查询。"""
        with self.get_connection() as conn:
            logging.info("开始数据库 ANALYZE...")
            conn.execute('ANALYZE')
            logging.info("数据库 ANALYZE 完成。")

    def get_database_info(self) -> dict:
        """
        获取数据库的元信息，如大小和表中的行数。

        Returns:
            dict: 包含数据库信息的字典。
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
            db_size = cursor.fetchone()[0]

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            tables = [row[0] for row in cursor.fetchall()]

            table_info = {}
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                table_info[table] = count

            return {
                'database_size_bytes': db_size,
                'tables': table_info
            }



