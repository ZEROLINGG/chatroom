"""config.py"""

class Config:
    class DbConfig:
        use = "sqlite"

        class Sqlite:
            path = "chat.db"

        class Mysql:
            host = "localhost"
            user = "root"
            passwd = "<PASSWORD>"
            database = "chat"
            charset = "utf8mb4"
