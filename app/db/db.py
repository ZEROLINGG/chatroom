"""app/db/db.py"""

from config import Config

DbConfig = Config.DbConfig


class DbWork:

    def __init__(self):
        if DbConfig.use == "mysql":
            # 使用 mysql 配置
            from .mysql.async_mysql_ import AsyncMySQLDB
            self.db = AsyncMySQLDB()
            pass
        elif DbConfig.use == "sqlite":
            from .sqlite.async_sqlite_ import AsyncSQLiteDB
            self.db = AsyncSQLiteDB(DbConfig.Sqlite.path)
        self.db.init_database()
