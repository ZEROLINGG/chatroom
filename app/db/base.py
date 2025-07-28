"""app/db/base.py"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, AsyncContextManager
from contextlib import asynccontextmanager
import logging

"""
app/db/base.py

数据库结构说明：
以下是聊天应用数据库的通用表结构，适用于异步 SQLite 和 MySQL 实现。
表结构设计支持高并发场景，包含用户、房间、消息、私聊消息、用户-房间关系和消息阅读状态。
所有实现必须支持外键约束以确保数据一致性，并为高频查询场景创建适当索引。

1. `user` 表
   存储用户信息。
   - user_uuid: STRING, 主键, 用户唯一标识 (UUID)
   - qq_number: STRING, 唯一, 用户QQ号
   - name: STRING, 非空, 用户名称
   - avatar_path: STRING, 头像路径
   - role: STRING, 默认 'user', 约束为 ('admin', 'super_admin', 'user')
   - password_hash: STRING, 密码哈希值
   - inviter: STRING, 邀请人UUID, 外键引用 user(user_uuid), 删除时置空
   - is_active: BOOLEAN, 默认 1, 用户是否活跃 (0/1)
   - last_login_at: INTEGER, 最后登录时间戳
   - created_at: INTEGER, 默认当前时间戳, 创建时间
   - updated_at: INTEGER, 默认当前时间戳, 更新时间
   索引:
     - idx_user_qq_number (qq_number)
     - idx_user_role (role)
     - idx_user_is_active (is_active)
     - idx_user_created_at (created_at)

2. `room` 表
   存储聊天房间信息。
   - room_uuid: STRING, 主键, 房间唯一标识 (UUID)
   - name: STRING, 非空, 房间名称
   - description: STRING, 房间描述
   - avatar_path: STRING, 房间头像路径
   - max_online_users: INTEGER, 默认 100, 最大在线用户数 (>0)
   - max_join_users: INTEGER, 默认 500, 最大加入用户数 (>0)
   - is_active: BOOLEAN, 默认 1, 房间是否活跃 (0/1)
   - created_at: INTEGER, 默认当前时间戳, 创建时间
   - updated_at: INTEGER, 默认当前时间戳, 更新时间
   - creator: STRING, 非空, 外键引用 user(user_uuid), 删除时级联
   索引:
     - idx_room_creator (creator)
     - idx_room_is_active (is_active)
     - idx_room_created_at (created_at)

3. `message` 表
   存储群聊/房间消息。
   - msg_uuid: STRING, 主键, 消息唯一标识 (UUID)
   - sender: STRING, 非空, 外键引用 user(user_uuid), 删除时级联
   - msg_type: STRING, 默认 'text', 约束为 ('text', 'image', 'audio', 'video', 'system', 'file')
   - content: STRING, 非空, 消息内容
   - room_uuid: STRING, 非空, 外键引用 room(room_uuid), 删除时级联
   - reply_to: STRING, 回复的消息UUID, 外键引用 message(msg_uuid), 删除时置空
   - file_path: STRING, 文件路径
   - file_size: INTEGER, 文件大小
   - is_deleted: BOOLEAN, 默认 0, 是否删除 (0/1)
   - created_at: INTEGER, 默认当前时间戳, 创建时间
   索引:
     - idx_message_sender (sender)
     - idx_message_room_uuid (room_uuid)
     - idx_message_created_at (created_at)
     - idx_message_msg_type (msg_type)
     - idx_message_is_deleted (is_deleted)
     - idx_message_reply_to (reply_to)
     - idx_message_room_time (room_uuid, created_at DESC)
     - idx_message_room_active (room_uuid, is_deleted, created_at DESC)

4. `private_message` 表
   存储私聊消息。
   - msg_uuid: STRING, 主键, 消息唯一标识 (UUID)
   - sender_uuid: STRING, 非空, 外键引用 user(user_uuid), 删除时级联
   - receiver_uuid: STRING, 非空, 外键引用 user(user_uuid), 删除时级联
   - msg_type: STRING, 默认 'text', 约束为 ('text', 'image', 'audio', 'video', 'system', 'file')
   - content: STRING, 非空, 消息内容
   - reply_to: STRING, 回复的消息UUID, 外键引用 private_message(msg_uuid), 删除时置空
   - file_path: STRING, 文件路径
   - file_size: INTEGER, 文件大小
   - is_deleted: BOOLEAN, 默认 0, 是否删除 (0/1)
   - is_read: BOOLEAN, 默认 0, 是否已读 (0/1)
   - created_at: INTEGER, 默认当前时间戳, 创建时间
   索引:
     - idx_pm_sender (sender_uuid)
     - idx_pm_receiver (receiver_uuid)
     - idx_pm_created_at (created_at)
     - idx_pm_is_read (is_read)
     - idx_pm_conversation (sender_uuid, receiver_uuid, created_at DESC)

5. `user_room` 表
   存储用户与房间的多对多关系。
   - id: INTEGER, 自增主键
   - user_uuid: STRING, 非空, 外键引用 user(user_uuid), 删除时级联
   - room_uuid: STRING, 非空, 外键引用 room(room_uuid), 删除时级联
   - role: STRING, 默认 'member', 约束为 ('owner', 'admin', 'member')
   - is_muted: BOOLEAN, 默认 0, 是否禁言 (0/1)
   - joined_at: INTEGER, 默认当前时间戳, 加入时间
   - left_at: INTEGER, 退出时间 (可为空)
   约束:
     - UNIQUE(user_uuid, room_uuid), 确保用户在同一房间唯一
   索引:
     - idx_user_room_user (user_uuid)
     - idx_user_room_room (room_uuid)
     - idx_user_room_joined_at (joined_at)
     - idx_user_room_left_at (left_at)

6. `message_read_status` 表
   存储消息阅读状态。
   - id: INTEGER, 自增主键
   - user_uuid: STRING, 非空, 外键引用 user(user_uuid), 删除时级联
   - message_uuid: STRING, 非空, 外键引用 message(msg_uuid), 删除时级联
   - room_uuid: STRING, 非空, 外键引用 room(room_uuid), 删除时级联
   - read_at: INTEGER, 默认当前时间戳, 阅读时间
   约束:
     - UNIQUE(user_uuid, message_uuid), 确保用户对同一消息的阅读状态唯一
   索引:
     - idx_read_status_user (user_uuid)
     - idx_read_status_room (room_uuid)
     - idx_read_status_message (message_uuid)

注意:
- 时间戳字段使用 Unix 时间戳 (INTEGER 类型)，默认值为当前时间戳。
- 外键约束必须支持级联删除或置空，以确保数据一致性。
- BOOLEAN 类型在 SQLite 中用 INTEGER (0/1) 表示，在 MySQL 中用 TINYINT (0/1) 或 BOOLEAN。
- STRING 类型在 SQLite 中用 TEXT，在 MySQL 中用 VARCHAR 或 CHAR（需指定长度）。
- 索引为高频查询优化（如消息按时间排序、房间活跃消息），具体实现可根据数据库引擎调整。
- 各实现需确保并发安全（如 SQLite 的连接管理和 MySQL 的事务隔离级别）。
"""


class AbstractAsyncDB(ABC):
    """
    异步数据库操作的抽象基类，提供通用的数据库操作接口。
    具体数据库实现（如 SQLite 或 MySQL）需继承此类并实现所有抽象方法。
    """

    def __init__(self, db_config: Dict[str, Any]):
        """
        初始化抽象异步数据库。

        Args:
            db_config (Dict[str, Any]): 数据库配置字典，具体内容由子类定义。
        """
        self.db_config = db_config
        self._initialized = False
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    async def init_database(self):
        """
        异步初始化数据库，创建表结构和索引。
        如果数据库已初始化，则直接返回。
        """
        pass

    @abstractmethod
    @asynccontextmanager
    async def get_connection(self) -> AsyncContextManager:
        """
        获取数据库连接的异步上下文管理器。
        每次调用返回一个新的连接，确保异步操作的正确性。

        Returns:
            AsyncContextManager: 数据库连接的上下文管理器。
        """
        pass

    @abstractmethod
    async def execute_transaction(self, operations: List[tuple]) -> bool:
        """
        在单个事务中异步执行多个 SQL 操作。

        Args:
            operations (List[tuple]): 操作列表，每个元素是 (sql, params) 的元组。

        Returns:
            bool: 成功返回 True，失败返回 False。
        """
        pass

    @abstractmethod
    async def get_database_info(self) -> dict:
        """
        异步获取数据库的元信息，如大小和表中的行数。

        Returns:
            dict: 包含数据库信息的字典。
        """
        pass

    # --- 业务逻辑方法 ---

    @abstractmethod
    async def create_user(self, user_data: Dict[str, Any]) -> str:
        """
        异步创建用户。

        Args:
            user_data (Dict[str, Any]): 用户数据字典。

        Returns:
            str: 创建的用户 UUID，失败返回空字符串。
        """
        pass

    @abstractmethod
    async def get_user_by_uuid(self, user_uuid: str) -> Optional[Dict[str, Any]]:
        """
        异步根据 UUID 获取用户信息。

        Args:
            user_uuid (str): 用户 UUID。

        Returns:
            Optional[Dict[str, Any]]: 用户信息字典，不存在返回 None。
        """
        pass

    @abstractmethod
    async def get_user_by_qq_number(self, qq_number: str) -> Optional[Dict[str, Any]]:
        """
        异步根据 QQ 号获取用户信息。

        Args:
            qq_number (str): 用户的 QQ 号。

        Returns:
            Optional[Dict[str, Any]]: 用户信息字典，不存在返回 None。
        """
        pass

    @abstractmethod
    async def update_user(self, user_uuid: str, update_data: Dict[str, Any]) -> bool:
        """
        异步更新用户信息。

        Args:
            user_uuid (str): 用户 UUID。
            update_data (Dict[str, Any]): 要更新的数据。

        Returns:
            bool: 更新成功返回 True，失败返回 False。
        """
        pass

    @abstractmethod
    async def create_room(self, room_data: Dict[str, Any]) -> str:
        """
        异步创建房间。

        Args:
            room_data (Dict[str, Any]): 房间数据字典。

        Returns:
            str: 创建的房间 UUID，失败返回空字符串。
        """
        pass

    @abstractmethod
    async def send_message(self, message_data: Dict[str, Any]) -> str:
        """
        异步发送消息到房间。

        Args:
            message_data (Dict[str, Any]): 消息数据字典。

        Returns:
            str: 创建的消息 UUID，失败返回空字符串。
        """
        pass

    @abstractmethod
    async def get_room_messages(self, room_uuid: str, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """
        异步获取房间消息（分页）。

        Args:
            room_uuid (str): 房间 UUID。
            limit (int): 每页消息数量，默认 50。
            offset (int): 偏移量，默认 0。

        Returns:
            List[Dict[str, Any]]: 消息列表。
        """
        pass

    @abstractmethod
    async def send_private_message(self, message_data: Dict[str, Any]) -> str:
        """
        异步发送私聊消息。

        Args:
            message_data (Dict[str, Any]): 私聊消息数据字典。

        Returns:
            str: 创建的消息 UUID，失败返回空字符串。
        """
        pass

    @abstractmethod
    async def get_private_message_users(self, user_uuid: str) -> List[str]:
        """
        异步获取与该用户有私聊记录的用户 UUID 列表。

        Args:
            user_uuid (str): 用户 UUID。

        Returns:
            List[str]: 用户 UUID 列表。
        """
        pass

    @abstractmethod
    async def get_private_messages(self, user_uuid1: str, user_uuid2: str, limit: int = 50, offset: int = 0) -> List[
        Dict[str, Any]]:
        """
        异步获取两个用户之间的私聊消息（分页）。

        Args:
            user_uuid1 (str): 用户1 UUID。
            user_uuid2 (str): 用户2 UUID。
            limit (int): 每页消息数量，默认 50。
            offset (int): 偏移量，默认 0。

        Returns:
            List[Dict[str, Any]]: 私聊消息列表。
        """
        pass

    @abstractmethod
    async def join_room(self, user_uuid: str, room_uuid: str) -> bool:
        """
        异步用户加入房间。

        Args:
            user_uuid (str): 用户 UUID。
            room_uuid (str): 房间 UUID。

        Returns:
            bool: 加入成功返回 True，失败返回 False。
        """
        pass

    @abstractmethod
    async def leave_room(self, user_uuid: str, room_uuid: str) -> bool:
        """
        异步用户退出房间。

        Args:
            user_uuid (str): 用户 UUID。
            room_uuid (str): 房间 UUID。

        Returns:
            bool: 退出成功返回 True，失败返回 False。
        """
        pass
