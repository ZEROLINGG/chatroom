"""app/db/sqlite/async_sqlite_.py (异步版本)"""

import aiosqlite
import uuid
import os
import asyncio
from datetime import datetime, UTC
from typing import Optional, List, Dict, Any, AsyncContextManager
from contextlib import asynccontextmanager
import logging
import threading

from app.db.base import AbstractAsyncDB


# --- 异步最佳实践建议 ---
# 1. 使用 aiosqlite 库进行异步SQLite操作
# 2. 所有数据库操作都是异步的，需要使用 await 关键字
# 3. 连接管理通过异步上下文管理器实现
# ------------------------------------

class AsyncSQLiteDB(AbstractAsyncDB):
    """
    一个用于管理SQLite数据库的异步类，支持高并发异步操作。
    使用 aiosqlite 库提供完全的异步数据库访问。
    """

    def __init__(self, db_config: Dict[str, Any]):
        """
        初始化异步SQLite数据库连接。

        Args:
            db_config (Dict[str, Any]): 数据库配置。
        """
        super().__init__(db_config)
        self.db_path = db_config.get('db_path', 'chat.db')
        self._connection_lock = asyncio.Lock()
        self.logger.info(f"异步 SQLite 数据库将初始化于 {os.path.abspath(self.db_path)}")

    async def init_database(self):
        """
        异步初始化数据库，创建表结构和索引。
        如果表已存在，则不会重复创建。
        """
        if self._initialized:
            return

        async with self._connection_lock:
            if self._initialized:
                return

            async with aiosqlite.connect(self.db_path) as conn:
                # 启用外键支持和优化设置
                await conn.execute('PRAGMA foreign_keys = ON')
                await conn.execute('PRAGMA journal_mode = WAL')
                await conn.execute('PRAGMA synchronous = NORMAL')
                await conn.execute('PRAGMA cache_size = -64000')

                # --- 表定义 ---
                # 与同步版本保持完全一致的表结构

                # `user` 表
                await conn.execute('''
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
                        updated_at INTEGER DEFAULT (strftime('%s', 'now'))
                        -- FOREIGN KEY (inviter) REFERENCES user(user_uuid) ON DELETE SET NULL
                    )
                ''')

                # `room` 表
                await conn.execute('''
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
                await conn.execute('''
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
                await conn.execute('''
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
                await conn.execute('''
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
                await conn.execute('''
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
                await self._create_indexes(conn)
                await conn.commit()

            self._initialized = True
            logging.info(f"异步数据库已初始化于 {os.path.abspath(self.db_path)}")

    async def _create_indexes(self, conn):
        """异步创建索引以提高查询性能"""
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
            await conn.execute(index_sql)

    @asynccontextmanager
    async def get_connection(self) -> AsyncContextManager[aiosqlite.Connection]:
        """
        获取数据库连接的异步上下文管理器。
        每次调用都会创建一个新的连接，确保线程安全和异步操作的正确性。
        """
        if not self._initialized:
            await self.init_database()

        conn = None
        try:
            conn = await aiosqlite.connect(
                self.db_path,
                timeout=30.0
            )
            # 配置连接
            conn.row_factory = aiosqlite.Row
            await conn.execute('PRAGMA foreign_keys = ON')

            yield conn

        except Exception as e:
            if conn:
                await conn.rollback()
            print(f"异步数据库操作失败: {e}")
            raise
        finally:
            if conn:
                await conn.close()

    async def execute_transaction(self, operations: List[tuple]) -> bool:
        """
        在单个事务中异步执行多个SQL操作。

        Args:
            operations (List[tuple]): 一个操作列表，每个元素是一个 (sql, params) 的元组。

        Returns:
            bool: 成功返回 True，失败返回 False。
        """
        async with self.get_connection() as conn:
            try:
                await conn.execute('BEGIN TRANSACTION')
                for sql, params in operations:
                    await conn.execute(sql, params or ())
                await conn.commit()
                return True
            except Exception as e:
                await conn.rollback()
                print(f"异步事务失败: {e}")
                return False

    async def get_database_info(self) -> dict:
        """
        异步获取数据库的元信息，如大小和表中的行数。

        Returns:
            dict: 包含数据库信息的字典。
        """
        async with self.get_connection() as conn:
            # 获取数据库大小
            async with conn.execute(
                    "SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()") as cursor:
                result = await cursor.fetchone()
                db_size = result[0] if result else 0

            # 获取所有表名
            async with conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'") as cursor:
                tables = [row[0] async for row in cursor]

            # 获取每个表的记录数
            table_info = {}
            for table in tables:
                async with conn.execute(f"SELECT COUNT(*) FROM {table}") as cursor:
                    result = await cursor.fetchone()
                    table_info[table] = result[0] if result else 0

            return {
                'database_size_bytes': db_size,
                'tables': table_info
            }

    # --- 业务逻辑方法 ---

    async def create_user(self, user_data: Dict[str, Any]) -> str:
        """
        异步创建用户。

        Args:
            user_data (Dict[str, Any]): 用户数据字典。

        Returns:
            str: 创建的用户UUID，失败则返回空字符串。
        """
        user_uuid = str(uuid.uuid4())
        current_timestamp = int(datetime.now(UTC).timestamp())

        try:
            async with self.get_connection() as conn:
                await conn.execute('''
                    INSERT INTO user (user_uuid, qq_number, name, avatar_path, role,
                                    password_hash, inviter, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    user_uuid,
                    user_data.get('qq_number'),
                    user_data.get('name'),
                    user_data.get('avatar_path'),
                    user_data.get('role', 'user'),
                    user_data.get('password_hash'),
                    user_data.get('inviter'),
                    current_timestamp,
                    current_timestamp
                ))
                await conn.commit()
                logging.info(f"用户创建成功: {user_uuid}")
                return user_uuid
        except Exception as e:
            print(f"创建用户失败: {e}")
            return ""

    async def get_user_by_uuid(self, user_uuid: str) -> Optional[Dict[str, Any]]:
        """
        异步根据UUID获取用户信息。

        Args:
            user_uuid (str): 用户UUID。

        Returns:
            Optional[Dict[str, Any]]: 用户信息字典，不存在则返回None。
        """
        try:
            async with self.get_connection() as conn:
                async with conn.execute(
                        'SELECT * FROM user WHERE user_uuid = ? AND is_active = 1',
                        (user_uuid,)
                ) as cursor:
                    row = await cursor.fetchone()
                    return dict(row) if row else None
        except Exception as e:
            print(f"获取用户失败: {e}")
            return None

    async def get_user_by_qq_number(self, qq_number: str) -> Optional[Dict[str, Any]]:
        """
        异步根据QQ号获取用户信息。
        Args:
            qq_number (str): 用户的QQ号。
        Returns:
            Optional[Dict[str, Any]]: 用户信息字典，如果用户不存在或不活跃则返回None。
        """
        try:
            async with self.get_connection() as conn:
                async with conn.execute(
                        'SELECT * FROM user WHERE qq_number = ? AND is_active = 1',
                        (qq_number,)
                ) as cursor:
                    row = await cursor.fetchone()
                    return dict(row) if row else None
        except Exception as e:
            print(f"获取用户（通过QQ号）失败: {e}")
            return None

    async def update_user(self, user_uuid: str, update_data: Dict[str, Any]) -> bool:
        """
        异步更新用户信息。

        Args:
            user_uuid (str): 用户UUID。
            update_data (Dict[str, Any]): 要更新的数据。

        Returns:
            bool: 更新成功返回True，失败返回False。
        """
        if not update_data:
            return False

        # 添加updated_at时间戳
        update_data['updated_at'] = int(datetime.now(UTC).timestamp())

        # 构建动态SQL
        fields = list(update_data.keys())
        values = list(update_data.values())
        values.append(user_uuid)  # WHERE条件的值

        set_clause = ', '.join([f"{field} = ?" for field in fields])
        sql = f"UPDATE user SET {set_clause} WHERE user_uuid = ?"

        try:
            async with self.get_connection() as conn:
                await conn.execute(sql, values)
                await conn.commit()
                logging.info(f"用户更新成功: {user_uuid}")
                return True
        except Exception as e:
            print(f"更新用户失败: {e}")
            return False

    async def create_room(self, room_data: Dict[str, Any]) -> str:
        """
        异步创建房间。

        Args:
            room_data (Dict[str, Any]): 房间数据字典。

        Returns:
            str: 创建的房间UUID，失败则返回空字符串。
        """
        room_uuid = str(uuid.uuid4())
        current_timestamp = int(datetime.now(UTC).timestamp())

        try:
            async with self.get_connection() as conn:
                # 创建房间
                await conn.execute('''
                    INSERT INTO room (room_uuid, name, description, avatar_path, 
                                    max_online_users, max_join_users, creator, 
                                    created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    room_uuid,
                    room_data.get('name'),
                    room_data.get('description'),
                    room_data.get('avatar_path'),
                    room_data.get('max_online_users', 100),
                    room_data.get('max_join_users', 500),
                    room_data.get('creator'),
                    current_timestamp,
                    current_timestamp
                ))

                # 将创建者添加为房间所有者
                await conn.execute('''
                    INSERT INTO user_room (user_uuid, room_uuid, role, joined_at)
                    VALUES (?, ?, 'owner', ?)
                ''', (room_data.get('creator'), room_uuid, current_timestamp))

                await conn.commit()
                logging.info(f"房间创建成功: {room_uuid}")
                return room_uuid
        except Exception as e:
            print(f"创建房间失败: {e}")
            return ""

    async def send_message(self, message_data: Dict[str, Any]) -> str:
        """
        异步发送消息到房间。

        Args:
            message_data (Dict[str, Any]): 消息数据字典。

        Returns:
            str: 创建的消息UUID，失败则返回空字符串。
        """
        msg_uuid = str(uuid.uuid4())
        current_timestamp = int(datetime.now(UTC).timestamp())

        try:
            async with self.get_connection() as conn:
                await conn.execute('''
                    INSERT INTO message (msg_uuid, sender, msg_type, content, room_uuid, 
                                       reply_to, file_path, file_size, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    msg_uuid,
                    message_data.get('sender'),
                    message_data.get('msg_type', 'text'),
                    message_data.get('content'),
                    message_data.get('room_uuid'),
                    message_data.get('reply_to'),
                    message_data.get('file_path'),
                    message_data.get('file_size'),
                    current_timestamp
                ))
                await conn.commit()
                logging.info(f"消息发送成功: {msg_uuid}")
                return msg_uuid
        except Exception as e:
            print(f"发送消息失败: {e}")
            return ""

    async def get_room_messages(self, room_uuid: str, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """
        异步获取房间消息（分页）。

        Args:
            room_uuid (str): 房间UUID。
            limit (int): 每页消息数量。
            offset (int): 偏移量。

        Returns:
            List[Dict[str, Any]]: 消息列表。
        """
        try:
            async with self.get_connection() as conn:
                async with conn.execute('''
                    SELECT m.*, u.name as sender_name, u.avatar_path as sender_avatar
                    FROM message m
                    LEFT JOIN user u ON m.sender = u.user_uuid
                    WHERE m.room_uuid = ? AND m.is_deleted = 0
                    ORDER BY m.created_at DESC
                    LIMIT ? OFFSET ?
                ''', (room_uuid, limit, offset)) as cursor:
                    return [dict(row) async for row in cursor]
        except Exception as e:
            print(f"获取房间消息失败: {e}")
            return []

    async def send_private_message(self, message_data: Dict[str, Any]) -> str:
        """
        异步发送私聊消息
        :param message_data: 私聊消息数据字典，包含 sender_uuid, receiver_uuid, content 等字段
        :return: 创建的消息UUID，失败则返回空字符串
        """
        msg_uuid = str(uuid.uuid4())
        current_timestamp = int(datetime.now(UTC).timestamp())

        try:
            async with self.get_connection() as conn:
                await conn.execute('''
                    INSERT INTO private_message (msg_uuid, sender_uuid, receiver_uuid, msg_type, content, 
                                               reply_to, file_path, file_size, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    msg_uuid,
                    message_data.get('sender_uuid'),
                    message_data.get('receiver_uuid'),
                    message_data.get('msg_type', 'text'),
                    message_data.get('content'),
                    message_data.get('reply_to'),
                    message_data.get('file_path'),
                    message_data.get('file_size'),
                    current_timestamp
                ))
                await conn.commit()
                logging.info(f"私聊消息发送成功: {msg_uuid}")
                return msg_uuid
        except Exception as e:
            print(f"发送私聊消息失败: {e}")
            return ""

    async def get_private_message_users(self, user_uuid: str) -> List[str]:
        """
        获取与该用户有私聊记录的用户
        :param user_uuid: 用户UUID
        :return: 对应的用户UUID列表
        """
        try:
            async with self.get_connection() as conn:
                async with conn.execute('''
                    SELECT DISTINCT receiver_uuid AS user_uuid 
                    FROM private_message 
                    WHERE sender_uuid = ?
                    UNION
                    SELECT DISTINCT sender_uuid AS user_uuid 
                    FROM private_message 
                    WHERE receiver_uuid = ?
                ''', (user_uuid, user_uuid)) as cursor:
                    rows = await cursor.fetchall()
                    return [row['user_uuid'] for row in rows]
        except Exception as e:
            print(f"获取私聊用户列表失败: {e}")
            return []

    async def get_private_messages(self, user_uuid1: str, user_uuid2: str, limit: int = 50, offset: int = 0) -> List[
        Dict[str, Any]]:
        """
        异步获取私聊消息（分页）
        :param user_uuid1: 用户1 UUID
        :param user_uuid2: 用户2 UUID
        :param limit: 每页消息数量，默认50
        :param offset: 偏移量，默认0
        :return: 私聊消息列表，每个消息包含详细信息
        """
        try:
            async with self.get_connection() as conn:
                async with conn.execute('''
                    SELECT pm.*, 
                           s.name AS sender_name, s.avatar_path AS sender_avatar,
                           r.name AS receiver_name, r.avatar_path AS receiver_avatar
                    FROM private_message pm
                    LEFT JOIN user s ON pm.sender_uuid = s.user_uuid
                    LEFT JOIN user r ON pm.receiver_uuid = r.user_uuid
                    WHERE (pm.sender_uuid = ? AND pm.receiver_uuid = ?) 
                       OR (pm.sender_uuid = ? AND pm.receiver_uuid = ?)
                    AND pm.is_deleted = 0
                    ORDER BY pm.created_at DESC
                    LIMIT ? OFFSET ?
                ''', (user_uuid1, user_uuid2, user_uuid2, user_uuid1, limit, offset)) as cursor:
                    return [dict(row) async for row in cursor]
        except Exception as e:
            print(f"获取私聊消息失败: {e}")
            return []

    async def join_room(self, user_uuid: str, room_uuid: str) -> bool:
        """
        异步用户加入房间。

        Args:
            user_uuid (str): 用户UUID。
            room_uuid (str): 房间UUID。

        Returns:
            bool: 加入成功返回True，失败返回False。
        """
        current_timestamp = int(datetime.now(UTC).timestamp())

        try:
            async with self.get_connection() as conn:
                await conn.execute('''
                    INSERT OR REPLACE INTO user_room (user_uuid, room_uuid, role, joined_at, left_at)
                    VALUES (?, ?, 'member', ?, NULL)
                ''', (user_uuid, room_uuid, current_timestamp))
                await conn.commit()
                logging.info(f"用户 {user_uuid} 成功加入房间 {room_uuid}")
                return True
        except Exception as e:
            print(f"用户加入房间失败: {e}")
            return False

    async def leave_room(self, user_uuid: str, room_uuid: str) -> bool:
        """
        异步用户退出房间。

        Args:
            user_uuid (str): 用户UUID。
            room_uuid (str): 房间UUID。

        Returns:
            bool: 退出成功返回True，失败返回False。
        """
        current_timestamp = int(datetime.now(UTC).timestamp())

        try:
            async with self.get_connection() as conn:
                await conn.execute('''
                    UPDATE user_room 
                    SET left_at = ? 
                    WHERE user_uuid = ? AND room_uuid = ? AND left_at IS NULL
                ''', (current_timestamp, user_uuid, room_uuid))
                await conn.commit()
                logging.info(f"用户 {user_uuid} 成功退出房间 {room_uuid}")
                return True
        except Exception as e:
            print(f"用户退出房间失败: {e}")
            return False
