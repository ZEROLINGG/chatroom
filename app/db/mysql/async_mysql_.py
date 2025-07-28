"""app/db/mysql/async_mysql_.py (异步版本)"""

import aiomysql
import uuid
import asyncio
from datetime import datetime, UTC
from typing import Optional, List, Dict, Any, AsyncContextManager
from contextlib import asynccontextmanager
import logging

from app.db.base import AbstractAsyncDB


# --- 异步最佳实践建议 ---
# 1. 使用 aiomysql 库进行异步MySQL操作
# 2. 所有数据库操作都是异步的，需要使用 await 关键字
# 3. 连接管理通过异步上下文管理器实现
# 4. 使用连接池提高性能
# ------------------------------------

class AsyncMySQLDB(AbstractAsyncDB):
    """
    一个用于管理MySQL数据库的异步类，支持高并发异步操作。
    使用 aiomysql 库提供完全的异步数据库访问，并支持连接池。
    """

    def __init__(self, db_config: Dict[str, Any]):
        """
        初始化异步MySQL数据库连接。

        Args:
            db_config (Dict[str, Any]): 数据库配置字典，包含host, port, user, password, database等。
        """
        super().__init__(db_config)
        self.host = db_config.get('host', 'localhost')
        self.port = db_config.get('port', 3306)
        self.user = db_config.get('user', 'root')
        self.password = db_config.get('password', '')
        self.database = db_config.get('database', 'chat_db')
        self.charset = db_config.get('charset', 'utf8mb4')
        self.pool_size = db_config.get('pool_size', 10)
        self.pool_max_size = db_config.get('pool_max_size', 20)

        self._pool = None
        self._connection_lock = asyncio.Lock()
        self.logger.info(f"异步 MySQL 数据库将连接到 {self.host}:{self.port}/{self.database}")

    async def _create_pool(self):
        """创建连接池"""
        if self._pool is None:
            self._pool = await aiomysql.create_pool(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                db=self.database,
                charset=self.charset,
                minsize=self.pool_size,
                maxsize=self.pool_max_size,
                autocommit=False,
                connect_timeout=30,
                pool_recycle=3600  # 1小时回收连接
            )

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

            await self._create_pool()

            async with self.get_connection() as conn:
                async with conn.cursor() as cursor:
                    # --- 表定义 ---
                    # 与SQLite版本保持功能一致，但使用MySQL语法

                    # `user` 表
                    await cursor.execute('''
                        CREATE TABLE IF NOT EXISTS user (
                            user_uuid VARCHAR(36) PRIMARY KEY,
                            qq_number VARCHAR(20) UNIQUE,
                            name VARCHAR(100) NOT NULL,
                            avatar_path VARCHAR(500),
                            role ENUM('admin', 'super_admin', 'user') DEFAULT 'user',
                            password_hash VARCHAR(255),
                            inviter VARCHAR(36),
                            is_active TINYINT(1) DEFAULT 1,
                            last_login_at BIGINT,
                            created_at BIGINT DEFAULT (UNIX_TIMESTAMP()),
                            updated_at BIGINT DEFAULT (UNIX_TIMESTAMP()),
                            INDEX idx_user_qq_number (qq_number),
                            INDEX idx_user_role (role),
                            INDEX idx_user_is_active (is_active),
                            INDEX idx_user_created_at (created_at),
                            FOREIGN KEY (inviter) REFERENCES user(user_uuid) ON DELETE SET NULL
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    ''')

                    # `room` 表
                    await cursor.execute('''
                        CREATE TABLE IF NOT EXISTS room (
                            room_uuid VARCHAR(36) PRIMARY KEY,
                            name VARCHAR(100) NOT NULL,
                            description TEXT,
                            avatar_path VARCHAR(500),
                            max_online_users INT DEFAULT 100 CHECK (max_online_users > 0),
                            max_join_users INT DEFAULT 500 CHECK (max_join_users > 0),
                            is_active TINYINT(1) DEFAULT 1,
                            created_at BIGINT DEFAULT (UNIX_TIMESTAMP()),
                            updated_at BIGINT DEFAULT (UNIX_TIMESTAMP()),
                            creator VARCHAR(36) NOT NULL,
                            INDEX idx_room_creator (creator),
                            INDEX idx_room_is_active (is_active),
                            INDEX idx_room_created_at (created_at),
                            FOREIGN KEY (creator) REFERENCES user(user_uuid) ON DELETE CASCADE
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    ''')

                    # `message` 表（用于群聊/房间聊天）
                    await cursor.execute('''
                        CREATE TABLE IF NOT EXISTS message (
                            msg_uuid VARCHAR(36) PRIMARY KEY,
                            sender VARCHAR(36) NOT NULL,
                            msg_type ENUM('text', 'image', 'audio', 'video', 'system', 'file') DEFAULT 'text',
                            content TEXT NOT NULL,
                            room_uuid VARCHAR(36) NOT NULL,
                            reply_to VARCHAR(36),
                            file_path VARCHAR(500),
                            file_size BIGINT,
                            is_deleted TINYINT(1) DEFAULT 0,
                            created_at BIGINT DEFAULT (UNIX_TIMESTAMP()),
                            INDEX idx_message_sender (sender),
                            INDEX idx_message_room_uuid (room_uuid),
                            INDEX idx_message_created_at (created_at),
                            INDEX idx_message_msg_type (msg_type),
                            INDEX idx_message_is_deleted (is_deleted),
                            INDEX idx_message_reply_to (reply_to),
                            INDEX idx_message_room_time (room_uuid, created_at DESC),
                            INDEX idx_message_room_active (room_uuid, is_deleted, created_at DESC),
                            FOREIGN KEY (sender) REFERENCES user(user_uuid) ON DELETE CASCADE,
                            FOREIGN KEY (room_uuid) REFERENCES room(room_uuid) ON DELETE CASCADE,
                            FOREIGN KEY (reply_to) REFERENCES message(msg_uuid) ON DELETE SET NULL
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    ''')

                    # `private_message` 表
                    await cursor.execute('''
                        CREATE TABLE IF NOT EXISTS private_message (
                            msg_uuid VARCHAR(36) PRIMARY KEY,
                            sender_uuid VARCHAR(36) NOT NULL,
                            receiver_uuid VARCHAR(36) NOT NULL,
                            msg_type ENUM('text', 'image', 'audio', 'video', 'system', 'file') DEFAULT 'text',
                            content TEXT NOT NULL,
                            reply_to VARCHAR(36),
                            file_path VARCHAR(500),
                            file_size BIGINT,
                            is_deleted TINYINT(1) DEFAULT 0,
                            is_read TINYINT(1) DEFAULT 0,
                            created_at BIGINT DEFAULT (UNIX_TIMESTAMP()),
                            INDEX idx_pm_sender (sender_uuid),
                            INDEX idx_pm_receiver (receiver_uuid),
                            INDEX idx_pm_created_at (created_at),
                            INDEX idx_pm_is_read (is_read),
                            INDEX idx_pm_conversation (sender_uuid, receiver_uuid, created_at DESC),
                            FOREIGN KEY (sender_uuid) REFERENCES user(user_uuid) ON DELETE CASCADE,
                            FOREIGN KEY (receiver_uuid) REFERENCES user(user_uuid) ON DELETE CASCADE,
                            FOREIGN KEY (reply_to) REFERENCES private_message(msg_uuid) ON DELETE SET NULL
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    ''')

                    # `user_room` 连接表（多对多关系）
                    await cursor.execute('''
                        CREATE TABLE IF NOT EXISTS user_room (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            user_uuid VARCHAR(36) NOT NULL,
                            room_uuid VARCHAR(36) NOT NULL,
                            role ENUM('owner', 'admin', 'member') DEFAULT 'member',
                            is_muted TINYINT(1) DEFAULT 0,
                            joined_at BIGINT DEFAULT (UNIX_TIMESTAMP()),
                            left_at BIGINT,
                            INDEX idx_user_room_user (user_uuid),
                            INDEX idx_user_room_room (room_uuid),
                            INDEX idx_user_room_joined_at (joined_at),
                            INDEX idx_user_room_left_at (left_at),
                            UNIQUE KEY unique_user_room (user_uuid, room_uuid),
                            FOREIGN KEY (user_uuid) REFERENCES user(user_uuid) ON DELETE CASCADE,
                            FOREIGN KEY (room_uuid) REFERENCES room(room_uuid) ON DELETE CASCADE
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    ''')

                    # `message_read_status` 表
                    await cursor.execute('''
                        CREATE TABLE IF NOT EXISTS message_read_status (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            user_uuid VARCHAR(36) NOT NULL,
                            message_uuid VARCHAR(36) NOT NULL,
                            room_uuid VARCHAR(36) NOT NULL,
                            read_at BIGINT DEFAULT (UNIX_TIMESTAMP()),
                            INDEX idx_read_status_user (user_uuid),
                            INDEX idx_read_status_room (room_uuid),
                            INDEX idx_read_status_message (message_uuid),
                            UNIQUE KEY unique_user_message (user_uuid, message_uuid),
                            FOREIGN KEY (user_uuid) REFERENCES user(user_uuid) ON DELETE CASCADE,
                            FOREIGN KEY (message_uuid) REFERENCES message(msg_uuid) ON DELETE CASCADE,
                            FOREIGN KEY (room_uuid) REFERENCES room(room_uuid) ON DELETE CASCADE
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    ''')

                await conn.commit()

            self._initialized = True
            self.logger.info(f"异步MySQL数据库已初始化于 {self.host}:{self.port}/{self.database}")

    @asynccontextmanager
    async def get_connection(self) -> AsyncContextManager:
        """
        获取数据库连接的异步上下文管理器。
        使用连接池获取连接，确保高性能和线程安全。
        """
        if not self._initialized:
            await self.init_database()

        if self._pool is None:
            await self._create_pool()

        conn = None
        try:
            conn = await self._pool.acquire()
            yield conn
        except Exception as e:
            if conn:
                await conn.rollback()
            self.logger.error(f"异步MySQL数据库操作失败: {e}")
            raise
        finally:
            if conn:
                self._pool.release(conn)

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
                await conn.begin()
                async with conn.cursor() as cursor:
                    for sql, params in operations:
                        await cursor.execute(sql, params or ())
                await conn.commit()
                return True
            except Exception as e:
                await conn.rollback()
                self.logger.error(f"异步MySQL事务失败: {e}")
                return False

    async def get_database_info(self) -> dict:
        """
        异步获取数据库的元信息，如大小和表中的行数。

        Returns:
            dict: 包含数据库信息的字典。
        """
        async with self.get_connection() as conn:
            async with conn.cursor() as cursor:
                # 获取数据库大小
                await cursor.execute('''
                    SELECT ROUND(SUM(data_length + index_length) / 1024 / 1024, 1) AS db_size_mb
                    FROM information_schema.tables 
                    WHERE table_schema = %s
                ''', (self.database,))
                result = await cursor.fetchone()
                db_size = result[0] if result and result[0] else 0

                # 获取所有表名
                await cursor.execute('''
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = %s AND table_type = 'BASE TABLE'
                ''', (self.database,))
                tables = [row[0] for row in await cursor.fetchall()]

                # 获取每个表的记录数
                table_info = {}
                for table in tables:
                    await cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    result = await cursor.fetchone()
                    table_info[table] = result[0] if result else 0

                return {
                    'database_size_mb': db_size,
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
                async with conn.cursor() as cursor:
                    await cursor.execute('''
                        INSERT INTO user (user_uuid, qq_number, name, avatar_path, role, 
                                        password_hash, inviter, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                self.logger.info(f"用户创建成功: {user_uuid}")
                return user_uuid
        except Exception as e:
            self.logger.error(f"创建用户失败: {e}")
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
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute(
                        'SELECT * FROM user WHERE user_uuid = %s AND is_active = 1',
                        (user_uuid,)
                    )
                    row = await cursor.fetchone()
                    return dict(row) if row else None
        except Exception as e:
            self.logger.error(f"获取用户失败: {e}")
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
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute(
                        'SELECT * FROM user WHERE qq_number = %s AND is_active = 1',
                        (qq_number,)
                    )
                    row = await cursor.fetchone()
                    return dict(row) if row else None
        except Exception as e:
            self.logger.error(f"获取用户（通过QQ号）失败: {e}")
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

        set_clause = ', '.join([f"{field} = %s" for field in fields])
        sql = f"UPDATE user SET {set_clause} WHERE user_uuid = %s"

        try:
            async with self.get_connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(sql, values)
                await conn.commit()
                self.logger.info(f"用户更新成功: {user_uuid}")
                return True
        except Exception as e:
            self.logger.error(f"更新用户失败: {e}")
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
                async with conn.cursor() as cursor:
                    # 创建房间
                    await cursor.execute('''
                        INSERT INTO room (room_uuid, name, description, avatar_path, 
                                        max_online_users, max_join_users, creator, 
                                        created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    await cursor.execute('''
                        INSERT INTO user_room (user_uuid, room_uuid, role, joined_at)
                        VALUES (%s, %s, 'owner', %s)
                    ''', (room_data.get('creator'), room_uuid, current_timestamp))

                await conn.commit()
                self.logger.info(f"房间创建成功: {room_uuid}")
                return room_uuid
        except Exception as e:
            self.logger.error(f"创建房间失败: {e}")
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
                async with conn.cursor() as cursor:
                    await cursor.execute('''
                        INSERT INTO message (msg_uuid, sender, msg_type, content, room_uuid, 
                                           reply_to, file_path, file_size, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                self.logger.info(f"消息发送成功: {msg_uuid}")
                return msg_uuid
        except Exception as e:
            self.logger.error(f"发送消息失败: {e}")
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
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute('''
                        SELECT m.*, u.name as sender_name, u.avatar_path as sender_avatar
                        FROM message m
                        LEFT JOIN user u ON m.sender = u.user_uuid
                        WHERE m.room_uuid = %s AND m.is_deleted = 0
                        ORDER BY m.created_at DESC
                        LIMIT %s OFFSET %s
                    ''', (room_uuid, limit, offset))
                    rows = await cursor.fetchall()
                    return [dict(row) for row in rows]
        except Exception as e:
            self.logger.error(f"获取房间消息失败: {e}")
            return []

    async def send_private_message(self, message_data: Dict[str, Any]) -> str:
        """
        异步发送私聊消息

        Args:
            message_data: 私聊消息数据字典，包含 sender_uuid, receiver_uuid, content 等字段

        Returns:
            str: 创建的消息UUID，失败则返回空字符串
        """
        msg_uuid = str(uuid.uuid4())
        current_timestamp = int(datetime.now(UTC).timestamp())

        try:
            async with self.get_connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute('''
                        INSERT INTO private_message (msg_uuid, sender_uuid, receiver_uuid, msg_type, content, 
                                                   reply_to, file_path, file_size, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                self.logger.info(f"私聊消息发送成功: {msg_uuid}")
                return msg_uuid
        except Exception as e:
            self.logger.error(f"发送私聊消息失败: {e}")
            return ""

    async def get_private_message_users(self, user_uuid: str) -> List[str]:
        """
        获取与该用户有私聊记录的用户

        Args:
            user_uuid: 用户UUID

        Returns:
            List[str]: 对应的用户UUID列表
        """
        try:
            async with self.get_connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute('''
                        SELECT DISTINCT receiver_uuid AS user_uuid 
                        FROM private_message 
                        WHERE sender_uuid = %s
                        UNION
                        SELECT DISTINCT sender_uuid AS user_uuid 
                        FROM private_message 
                        WHERE receiver_uuid = %s
                    ''', (user_uuid, user_uuid))
                    rows = await cursor.fetchall()
                    return [row[0] for row in rows]
        except Exception as e:
            self.logger.error(f"获取私聊用户列表失败: {e}")
            return []

    async def get_private_messages(self, user_uuid1: str, user_uuid2: str, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """
        异步获取私聊消息（分页）

        Args:
            user_uuid1: 用户1 UUID
            user_uuid2: 用户2 UUID
            limit: 每页消息数量，默认50
            offset: 偏移量，默认0

        Returns:
            List[Dict[str, Any]]: 私聊消息列表，每个消息包含详细信息
        """
        try:
            async with self.get_connection() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute('''
                        SELECT pm.*, 
                               s.name AS sender_name, s.avatar_path AS sender_avatar,
                               r.name AS receiver_name, r.avatar_path AS receiver_avatar
                        FROM private_message pm
                        LEFT JOIN user s ON pm.sender_uuid = s.user_uuid
                        LEFT JOIN user r ON pm.receiver_uuid = r.user_uuid
                        WHERE (pm.sender_uuid = %s AND pm.receiver_uuid = %s) 
                           OR (pm.sender_uuid = %s AND pm.receiver_uuid = %s)
                        AND pm.is_deleted = 0
                        ORDER BY pm.created_at DESC
                        LIMIT %s OFFSET %s
                    ''', (user_uuid1, user_uuid2, user_uuid2, user_uuid1, limit, offset))
                    rows = await cursor.fetchall()
                    return [dict(row) for row in rows]
        except Exception as e:
            self.logger.error(f"获取私聊消息失败: {e}")
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
                async with conn.cursor() as cursor:
                    await cursor.execute('''
                        INSERT INTO user_room (user_uuid, room_uuid, role, joined_at, left_at)
                        VALUES (%s, %s, 'member', %s, NULL)
                        ON DUPLICATE KEY UPDATE 
                        joined_at = %s, left_at = NULL
                    ''', (user_uuid, room_uuid, current_timestamp, current_timestamp))
                await conn.commit()
                self.logger.info(f"用户 {user_uuid} 成功加入房间 {room_uuid}")
                return True
        except Exception as e:
            self.logger.error(f"用户加入房间失败: {e}")
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
                async with conn.cursor() as cursor:
                    await cursor.execute('''
                        UPDATE user_room 
                        SET left_at = %s 
                        WHERE user_uuid = %s AND room_uuid = %s AND left_at IS NULL
                    ''', (current_timestamp, user_uuid, room_uuid))
                await conn.commit()
                self.logger.info(f"用户 {user_uuid} 成功退出房间 {room_uuid}")
                return True
        except Exception as e:
            self.logger.error(f"用户退出房间失败: {e}")
            return False

    async def close(self):
        """
        关闭数据库连接池
        """
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None
            self.logger.info("MySQL连接池已关闭")

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.init_database()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()