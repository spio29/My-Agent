from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List


class FakeAsyncRedis:
    def __init__(self):
        self._strings: Dict[str, Any] = {}
        self._sets: Dict[str, set[str]] = defaultdict(set)
        self._lists: Dict[str, List[Any]] = defaultdict(list)
        self._sorted_sets: Dict[str, Dict[str, float]] = defaultdict(dict)
        self._streams: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._stream_counter = 0

    async def aclose(self) -> None:
        return None

    async def set(self, key: str, value: Any, ex: int | None = None, nx: bool = False) -> bool:
        if nx and key in self._strings:
            return False
        self._strings[key] = value
        return True

    async def setex(self, key: str, ttl: int, value: Any) -> bool:
        self._strings[key] = value
        return True

    async def get(self, key: str) -> Any:
        return self._strings.get(key)

    async def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            removed = False
            removed = self._strings.pop(key, None) is not None or removed
            removed = self._sets.pop(key, None) is not None or removed
            removed = self._lists.pop(key, None) is not None or removed
            removed = self._sorted_sets.pop(key, None) is not None or removed
            removed = self._streams.pop(key, None) is not None or removed
            if removed:
                deleted += 1
        return deleted

    async def sadd(self, key: str, *members: str) -> int:
        target = self._sets[key]
        before = len(target)
        target.update(str(member) for member in members)
        return len(target) - before

    async def smembers(self, key: str) -> set[str]:
        return set(self._sets.get(key, set()))

    async def srem(self, key: str, *members: str) -> int:
        target = self._sets.get(key, set())
        removed = 0
        for member in members:
            if str(member) in target:
                target.remove(str(member))
                removed += 1
        return removed

    async def sismember(self, key: str, member: str) -> bool:
        return str(member) in self._sets.get(key, set())

    async def scard(self, key: str) -> int:
        return len(self._sets.get(key, set()))

    async def lpush(self, key: str, *values: Any) -> int:
        target = self._lists[key]
        for value in values:
            target.insert(0, value)
        return len(target)

    async def rpush(self, key: str, *values: Any) -> int:
        target = self._lists[key]
        target.extend(values)
        return len(target)

    async def ltrim(self, key: str, start: int, stop: int) -> bool:
        target = self._lists.get(key, [])
        if not target:
            return True
        stop_index = None if stop == -1 else stop + 1
        self._lists[key] = target[start:stop_index]
        return True

    async def lrange(self, key: str, start: int, stop: int) -> List[Any]:
        target = self._lists.get(key, [])
        stop_index = None if stop == -1 else stop + 1
        return list(target[start:stop_index])

    async def lindex(self, key: str, index: int) -> Any:
        target = self._lists.get(key, [])
        try:
            return target[index]
        except IndexError:
            return None

    async def llen(self, key: str) -> int:
        return len(self._lists.get(key, []))

    async def xadd(self, key: str, fields: Dict[str, Any]) -> str:
        self._stream_counter += 1
        message_id = f"0-{self._stream_counter}"
        self._streams[key].append({"id": message_id, "fields": dict(fields)})
        return message_id

    async def xlen(self, key: str) -> int:
        return len(self._streams.get(key, []))

    async def zadd(self, key: str, mapping: Dict[str, float]) -> int:
        target = self._sorted_sets[key]
        added = 0
        for member, score in mapping.items():
            if member not in target:
                added += 1
            target[str(member)] = float(score)
        return added

    async def zcard(self, key: str) -> int:
        return len(self._sorted_sets.get(key, {}))

    async def zrevrange(self, key: str, start: int, stop: int) -> List[str]:
        target = self._sorted_sets.get(key, {})
        ordered = [
            member for member, _score in sorted(target.items(), key=lambda item: item[1], reverse=True)
        ]
        stop_index = None if stop == -1 else stop + 1
        return ordered[start:stop_index]
