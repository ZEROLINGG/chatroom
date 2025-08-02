import asyncio
import heapq
import time
from collections import defaultdict
from typing import Union, List, Any, Dict, Optional, Tuple


class Kv:
    """
    一个异步且线程安全的键值存储类，支持过期时间。
    针对大规模数据场景进行了性能优化。
    键统一为字符串类型，值可以是字符串、整数、布尔类型、字典或None。
    适用于需要并发访问共享数据的场景，例如存储聊天室用户的在线信息或加密密钥。
    """

    def __init__(self, cleanup_interval: int = 60, max_cleanup_batch: int = 1000):
        """
        初始化键值存储。
        
        :param cleanup_interval: 自动清理过期数据的间隔（秒）
        :param max_cleanup_batch: 每次清理的最大键数量
        """
        # 数据存储：{key: (value, expiry_time)}，expiry_time=-1表示永不过期
        self._data: Dict[str, Tuple[Any, float]] = {}

        # 过期时间堆：[(expiry_time, key), ...]，用于高效管理过期时间
        self._expiry_heap: List[Tuple[float, str]] = []

        # 读写锁：允许多个读操作并发执行
        self._rw_lock = RWLock()

        # 前缀索引：{prefix: set(keys)}，用于快速前缀查询
        self._prefix_index: Dict[str, set] = defaultdict(set)

        # 清理参数
        self._cleanup_interval = cleanup_interval
        self._max_cleanup_batch = max_cleanup_batch

        # 启动后台清理任务
        self._cleanup_task = None
        self._start_cleanup_task()

        # 用于标记对象是否被销毁
        self._destroyed = False

    def _start_cleanup_task(self):
        """启动后台清理任务"""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._background_cleanup())

    async def _background_cleanup(self):
        """后台定期清理过期数据"""
        try:
            while not self._destroyed:
                await asyncio.sleep(self._cleanup_interval)
                if not self._destroyed:
                    await self._cleanup_expired_batch()
        except asyncio.CancelledError:
            pass

    async def _cleanup_expired_batch(self):
        """批量清理过期数据，减少锁的持有时间"""
        current_time = time.time()
        expired_keys = []

        # 使用写锁，但尽量减少持有时间
        async with self._rw_lock.writer():
            # 从堆中取出已过期的键
            count = 0
            while (self._expiry_heap and
                   self._expiry_heap[0][0] != -1 and
                   self._expiry_heap[0][0] <= current_time and
                   count < self._max_cleanup_batch):

                expiry_time, key = heapq.heappop(self._expiry_heap)

                # 检查键是否仍然存在且过期时间匹配（避免重复删除）
                if key in self._data:
                    stored_value, stored_expiry = self._data[key]
                    if stored_expiry == expiry_time:  # 确保是同一个条目
                        expired_keys.append(key)
                        count += 1

            # 删除过期的键值对
            for key in expired_keys:
                if key in self._data:
                    del self._data[key]
                    self._remove_from_prefix_index(key)

    def _remove_from_prefix_index(self, key: str):
        """从前缀索引中移除键"""
        # 更新前缀索引（移除空集合以节省内存）
        to_remove = []
        for prefix, keys in self._prefix_index.items():
            if key in keys:
                keys.discard(key)
                if not keys:
                    to_remove.append(prefix)

        for prefix in to_remove:
            del self._prefix_index[prefix]

    def _add_to_prefix_index(self, key: str):
        """将键添加到前缀索引"""
        # 为了平衡内存和查询性能，只索引长度为1-4的前缀
        for i in range(1, min(len(key) + 1, 5)):
            prefix = key[:i]
            self._prefix_index[prefix].add(key)

    async def _cleanup_expired_immediate(self, keys_to_check: List[str] = None):
        """
        立即清理过期数据（内部方法）。
        注意：调用此方法前必须已经获得写锁。
        
        :param keys_to_check: 要检查的特定键列表，如果为None则检查堆顶的过期键
        """
        current_time = time.time()

        if keys_to_check:
            # 检查特定键
            for key in keys_to_check:
                if key in self._data:
                    value, expiry_time = self._data[key]
                    if expiry_time != -1 and current_time > expiry_time:
                        del self._data[key]
                        self._remove_from_prefix_index(key)
        else:
            # 检查堆顶的过期键（只检查少量以避免阻塞）
            checked = 0
            while (self._expiry_heap and
                   self._expiry_heap[0][0] != -1 and
                   self._expiry_heap[0][0] <= current_time and
                   checked < 10):  # 限制检查数量

                expiry_time, key = heapq.heappop(self._expiry_heap)

                if key in self._data:
                    stored_value, stored_expiry = self._data[key]
                    if stored_expiry == expiry_time:
                        del self._data[key]
                        self._remove_from_prefix_index(key)

                checked += 1

    async def add(self, key: str, value: Union[str, int, bool, dict, None], ttl: int = -1):
        """
        添加或更新一个键值对。如果键已存在，则更新其值和过期时间。
        
        :param key: 键，必须是字符串。
        :param value: 值，可以是字符串、整数、布尔值、字典或None。
        :param ttl: 存在时长（秒），-1表示永不过期（默认值）。
        :raises TypeError: 如果键或值的类型不正确。
        :raises ValueError: 如果ttl小于-1。
        """
        if not isinstance(key, str):
            raise TypeError("键 (key) 必须是字符串类型")
        if not isinstance(value, (str, int, bool, dict, type(None))):
            raise TypeError("值 (value) 必须是字符串、整数、布尔、字典或None类型")
        if ttl < -1:
            raise ValueError("ttl 必须是 -1（永不过期）或正整数（秒数）")

        async with self._rw_lock.writer():
            # 如果键已存在，从前缀索引中移除（稍后会重新添加）
            if key in self._data:
                self._remove_from_prefix_index(key)

            # 计算过期时间
            if ttl == -1:
                expiry_time = -1  # 永不过期
            else:
                expiry_time = time.time() + ttl
                # 添加到过期堆
                heapq.heappush(self._expiry_heap, (expiry_time, key))

            # 存储数据
            self._data[key] = (value, expiry_time)

            # 添加到前缀索引
            self._add_to_prefix_index(key)

    async def get(self, key: str, default: Any = None) -> Any:
        """
        根据键获取值。
        :param key: 要查找的键。
        :param default: 如果键不存在时返回的默认值。
        :return: 查找到的值或默认值。
        """
        async with self._rw_lock.reader():  # 使用读锁提高并发性
            if key in self._data:
                value, expiry_time = self._data[key]

                # 检查是否过期
                if expiry_time != -1 and time.time() > expiry_time:
                    # 需要写锁来删除过期数据
                    pass  # 先返回默认值，让后台任务清理
                else:
                    return value

        # 如果需要清理过期数据，获取写锁
        async with self._rw_lock.writer():
            if key in self._data:
                value, expiry_time = self._data[key]
                if expiry_time != -1 and time.time() > expiry_time:
                    del self._data[key]
                    self._remove_from_prefix_index(key)
                    return default
                else:
                    return value
            return default

    async def delete(self, key: str):
        """
        根据键删除一个键值对。如果键不存在，则不执行任何操作。
        
        :param key: 要删除的键。
        """
        async with self._rw_lock.writer():
            if key in self._data:
                del self._data[key]
                self._remove_from_prefix_index(key)

    async def exists(self, key: str) -> bool:
        """
        检查指定的键是否存在。
        
        :param key: 要检查的键。
        :return: 如果键存在则返回 True，否则返回 False。
        """
        async with self._rw_lock.reader():
            if key in self._data:
                value, expiry_time = self._data[key]
                if expiry_time == -1 or time.time() <= expiry_time:
                    return True

        # 如果可能过期，使用写锁检查并清理
        async with self._rw_lock.writer():
            if key in self._data:
                value, expiry_time = self._data[key]
                if expiry_time != -1 and time.time() > expiry_time:
                    del self._data[key]
                    self._remove_from_prefix_index(key)
                    return False
                return True
            return False

    async def keys(self) -> List[str]:
        """
        返回所有键的列表。
        
        :return: 包含所有键的列表。
        """
        async with self._rw_lock.reader():
            # 快速返回当前键，让后台任务处理过期清理
            current_time = time.time()
            valid_keys = []

            for key, (value, expiry_time) in self._data.items():
                if expiry_time == -1 or current_time <= expiry_time:
                    valid_keys.append(key)

            return valid_keys

    async def values(self) -> List[Union[str, int, bool, dict, None]]:
        """
        返回所有值的列表。
        
        :return: 包含所有值的列表。
        """
        async with self._rw_lock.reader():
            current_time = time.time()
            valid_values = []

            for key, (value, expiry_time) in self._data.items():
                if expiry_time == -1 or current_time <= expiry_time:
                    valid_values.append(value)

            return valid_values

    async def count_ka(self) -> int:
        """
        计算所有键值对的总数。
        
        :return: 键值对的总数。
        """
        async with self._rw_lock.reader():
            current_time = time.time()
            count = 0

            for key, (value, expiry_time) in self._data.items():
                if expiry_time == -1 or current_time <= expiry_time:
                    count += 1

            return count

    async def count_kh(self, head: str) -> int:
        """
        计算以指定字符串开头的键的数量。
        使用前缀索引优化性能。
        
        :param head: 要匹配的键名前缀。
        :return: 匹配的键的数量。
        """
        async with self._rw_lock.reader():
            # 使用前缀索引快速查找
            if head in self._prefix_index:
                candidate_keys = self._prefix_index[head]
            else:
                candidate_keys = [key for key in self._data.keys() if key.startswith(head)]

            current_time = time.time()
            count = 0

            for key in candidate_keys:
                if key in self._data:
                    value, expiry_time = self._data[key]
                    if expiry_time == -1 or current_time <= expiry_time:
                        count += 1

            return count

    async def keys_kh(self, head: str) -> List[str]:
        """
        返回所有以指定字符串开头的键的列表。
        使用前缀索引优化性能。
        
        :param head: 要匹配的键名前缀。
        :return: 包含所有匹配键的列表。
        """
        async with self._rw_lock.reader():
            # 使用前缀索引快速查找
            if head in self._prefix_index:
                candidate_keys = self._prefix_index[head]
            else:
                candidate_keys = [key for key in self._data.keys() if key.startswith(head)]

            current_time = time.time()
            valid_keys = []

            for key in candidate_keys:
                if key in self._data:
                    value, expiry_time = self._data[key]
                    if expiry_time == -1 or current_time <= expiry_time:
                        valid_keys.append(key)

            return valid_keys

    async def value_is_true(self, key: str) -> bool:
        """
        检查指定键的值是否为 True。
        
        :param key: 要检查的键。
        :return: 如果键存在、其值为布尔类型且值为 True，则返回 True。
                 在其他所有情况下（键不存在、值类型不正确或值为 False）均返回 False。
        """
        async with self._rw_lock.reader():
            if key in self._data:
                value, expiry_time = self._data[key]
                if (expiry_time == -1 or time.time() <= expiry_time) and isinstance(value, bool) and value is True:
                    return True
            return False

    async def get_ttl(self, key: str) -> Optional[int]:
        """
        获取指定键的剩余存在时间（秒）。
        
        :param key: 要查询的键。
        :return: 剩余时间（秒），-1表示永不过期，None表示键不存在。
        """
        async with self._rw_lock.reader():
            if key not in self._data:
                return None

            value, expiry_time = self._data[key]
            if expiry_time == -1:
                return -1

            remaining = int(expiry_time - time.time())
            if remaining <= 0:
                return None  # 已过期，视为不存在

            return remaining

    async def extend_ttl(self, key: str, additional_seconds: int) -> bool:
        """
        延长指定键的存在时间。
        
        :param key: 要延长的键。
        :param additional_seconds: 要添加的秒数。
        :return: 如果成功延长则返回True，键不存在则返回False。
        """
        async with self._rw_lock.writer():
            if key not in self._data:
                return False

            value, current_expiry = self._data[key]

            # 检查是否已过期
            if current_expiry != -1 and time.time() > current_expiry:
                del self._data[key]
                self._remove_from_prefix_index(key)
                return False

            if current_expiry == -1:
                # 永不过期的键，保持永不过期
                return True

            # 更新过期时间
            new_expiry = current_expiry + additional_seconds
            self._data[key] = (value, new_expiry)

            # 添加新的过期时间到堆
            heapq.heappush(self._expiry_heap, (new_expiry, key))

            return True

    async def clear(self):
        """
        清空所有键值对。
        """
        async with self._rw_lock.writer():
            self._data.clear()
            self._expiry_heap.clear()
            self._prefix_index.clear()

    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()

    async def close(self):
        """关闭存储并清理资源"""
        self._destroyed = True
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass


class RWLock:
    """读写锁实现，允许多个读者或一个写者"""

    def __init__(self):
        self._readers = 0
        self._writers = 0
        self._read_ready = asyncio.Condition()
        self._write_ready = asyncio.Condition()

    def reader(self):
        """获取读锁"""
        return _RLockManager(self)

    def writer(self):
        """获取写锁"""
        return _WLockManager(self)

    async def _acquire_read(self):
        """获取读锁"""
        async with self._read_ready:
            while self._writers > 0:
                await self._read_ready.wait()
            self._readers += 1

    async def _release_read(self):
        """释放读锁"""
        async with self._read_ready:
            self._readers -= 1
            if self._readers == 0:
                self._read_ready.notify_all()

    async def _acquire_write(self):
        """获取写锁"""
        async with self._write_ready:
            while self._writers > 0 or self._readers > 0:
                await self._write_ready.wait()
            self._writers += 1

    async def _release_write(self):
        """释放写锁"""
        async with self._write_ready:
            self._writers -= 1
            self._write_ready.notify_all()

        # 通知等待的读者
        async with self._read_ready:
            self._read_ready.notify_all()


class _RLockManager:
    """读锁上下文管理器"""

    def __init__(self, lock):
        self._lock = lock

    async def __aenter__(self):
        await self._lock._acquire_read()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._lock._release_read()


class _WLockManager:
    """写锁上下文管理器"""

    def __init__(self, lock):
        self._lock = lock

    async def __aenter__(self):
        await self._lock._acquire_write()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._lock._release_write()


# --- 示例用法 ---
async def main():
    async with Kv(cleanup_interval=30) as kv_store:  # 30秒清理间隔
        # 添加不同类型的数据，包含过期时间
        await kv_store.add("user:alice:online", True)  # 永不过期
        await kv_store.add("user:bob:online", False, ttl=60)  # 60秒后过期
        await kv_store.add("user:charlie:profile", {"name": "Charlie", "age": 25}, ttl=30)  # 30秒后过期
        await kv_store.add("temp:session", "abc123", ttl=10)  # 10秒后过期
        await kv_store.add("config:max_users", 100)  # 永不过期
        await kv_store.add("nullable:value", None)  # None值，永不过期

        print("--- 初始数据 ---")
        print(f"所有键: {await kv_store.keys()}")
        print(f"所有值: {await kv_store.values()}")

        # 获取数据
        print("\n--- 获取数据 ---")
        alice_online = await kv_store.get("user:alice:online")
        print(f"Alice 在线吗? {alice_online}")

        charlie_profile = await kv_store.get("user:charlie:profile")
        print(f"Charlie 的资料: {charlie_profile}")

        nullable_value = await kv_store.get("nullable:value")
        print(f"可空值: {nullable_value}")

        # 检查TTL
        print("\n--- 检查TTL ---")
        print(f"Alice TTL: {await kv_store.get_ttl('user:alice:online')}")
        print(f"Bob TTL: {await kv_store.get_ttl('user:bob:online')}")
        print(f"Charlie TTL: {await kv_store.get_ttl('user:charlie:profile')}")
        print(f"Session TTL: {await kv_store.get_ttl('temp:session')}")

        # 延长TTL
        print("\n--- 延长TTL ---")
        extended = await kv_store.extend_ttl("temp:session", 20)
        print(f"Session TTL 延长成功: {extended}")
        print(f"Session 新TTL: {await kv_store.get_ttl('temp:session')}")

        # 等待一些数据过期
        print("\n--- 等待过期 ---")
        print("等待15秒...")
        await asyncio.sleep(15)

        print(f"15秒后所有键: {await kv_store.keys()}")
        print(f"Charlie 的资料（可能已过期）: {await kv_store.get('user:charlie:profile', '已过期')}")

        # 计数
        print("\n--- 计数 ---")
        print(f"总键值对数量: {await kv_store.count_ka()}")
        print(f"以 'user:' 开头的键数量: {await kv_store.count_kh('user:')}")

        # 获取以特定前缀开头的键
        print("\n--- 获取特定键 ---")
        user_keys = await kv_store.keys_kh("user:")
        print(f"所有用户相关的键: {user_keys}")

        # 检查值为 True 的情况
        print("\n--- 检查布尔值 ---")
        print(f"Alice 的值是 True 吗? {await kv_store.value_is_true('user:alice:online')}")
        print(f"Bob 的值是 True 吗? {await kv_store.value_is_true('user:bob:online')}")


if __name__ == "__main__":
    # 在 Python 脚本中运行异步代码
    asyncio.run(main())
