"""app/db/db.py"""
import logging
from typing import Dict, Any

from app.db.base import AbstractAsyncDB
from app.db.sqlite.async_sqlite_ import AsyncSQLiteDB
from config import Config

DbConfig = Config.DbConfig


class DbWork:
    """
    数据库操作封装类，基于配置选择具体数据库实现，提供统一的异步操作接口。
    """

    def __init__(self):
        """
       初始化 DbWork 类，基于配置选择数据库实现。

       Args:
       """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.db = self._get_db_instance({'db_path': DbConfig.Sqlite.path})
        self.logger.info(f"DbWork 初始化，使用的数据库类型: {DbConfig.use}")

    def _get_db_instance(self, config: Dict[str, Any]) -> AbstractAsyncDB:
        """
        工厂方法，根据配置创建数据库实例。

        Args:
            config (Dict[str, Any]): 数据库配置字典。

        Returns:
            AbstractAsyncDB: 具体的数据库实现实例。

        Raises:
            ValueError: 如果 db_type 不支持。
        """
        db_type = DbConfig.use
        if db_type == 'sqlite':
            return AsyncSQLiteDB(db_config=config)
        elif db_type == 'mysql':
            # return AsyncMySQLDB(db_config=config)  # 待实现
            raise NotImplementedError("MySQL support is not yet implemented")
        else:
            raise ValueError(f"Unsupported database type: {db_type}")

    async def init_async(self):
        """
        初始化数据库，调用底层数据库实现的 init_database 方法。
        """
        await self.db.init_database()
        self.logger.info("数据库初始化完成")

    @classmethod
    async def create_async(cls) -> 'DbWork':
        """
        创建 DbWork 实例并初始化数据库。

        Returns:
            DbWork: 初始化完成的 DbWork 实例。
        """
        instance = cls()
        await instance.init_async()
        return instance

    @classmethod
    def create(cls) -> 'DbWork':
        instance = cls()
        instance.init_async()
        return instance

    def get_db(self) -> AbstractAsyncDB:
        return self.db
