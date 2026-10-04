"""WebSocket room bookkeeping.

One :class:`ConnectionManager` instance is shared by the whole process.  It
knows how to address everyone in a game ("room") and can target the host or a
single player.  Sending never holds the registry lock so a slow client cannot
stall a broadcast.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import WebSocket

from app.game.events import WSEventType, envelope

logger = logging.getLogger(__name__)

Role = Literal["host", "player"]


@dataclass
class Connection:
    """A single socket bound to either a host user or a joined player."""

    websocket: WebSocket
    role: Role
    game_pin: str
    game_id: int
    player_id: int | None = None
    user_id: int | None = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    @property
    def is_host(self) -> bool:
        return self.role == "host"


class ConnectionManager:
    def __init__(self) -> None:
        self._rooms: dict[str, dict[str, Connection]] = {}
        self._players: dict[int, Connection] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------ registry
    async def register(self, connection: Connection) -> None:
        async with self._lock:
            room = self._rooms.setdefault(connection.game_pin, {})
            # one live socket per player identity: evict a stale duplicate
            if connection.player_id is not None:
                existing = self._players.get(connection.player_id)
                if existing is not None and existing.id != connection.id:
                    room.pop(existing.id, None)
            room[connection.id] = connection
            if connection.player_id is not None:
                self._players[connection.player_id] = connection

    async def unregister(self, connection: Connection) -> None:
        async with self._lock:
            room = self._rooms.get(connection.game_pin)
            if room:
                room.pop(connection.id, None)
                if not room:
                    self._rooms.pop(connection.game_pin, None)
            if connection.player_id is not None:
                current = self._players.get(connection.player_id)
                if current is not None and current.id == connection.id:
                    self._players.pop(connection.player_id, None)

    # -------------------------------------------------------------- lookup
    def player_connection(self, player_id: int) -> Connection | None:
        return self._players.get(player_id)

    def is_player_connected(self, player_id: int) -> bool:
        return player_id in self._players

    def connected_player_ids(self, game_pin: str) -> set[int]:
        return {
            c.player_id
            for c in self._rooms.get(game_pin, {}).values()
            if c.player_id is not None
        }

    def host_connections(self, game_pin: str) -> list[Connection]:
        return [c for c in self._rooms.get(game_pin, {}).values() if c.is_host]

    def room_size(self, game_pin: str) -> int:
        return len(self._rooms.get(game_pin, {}))

    def all_rooms(self) -> dict[str, int]:
        return {pin: len(conns) for pin, conns in self._rooms.items()}

    # -------------------------------------------------------------- sending
    async def send(self, connection: Connection, event_type: WSEventType | str, payload: dict[str, Any] | None = None) -> bool:
        """Send one event.  Returns ``False`` if the socket was dead."""
        try:
            await connection.websocket.send_json(envelope(event_type, payload))
            return True
        except Exception:  # pragma: no cover - socket already gone
            return False

    async def broadcast(
        self,
        game_pin: str,
        event_type: WSEventType | str,
        payload: dict[str, Any] | None = None,
        *,
        exclude_player_id: int | None = None,
        include_hosts: bool = True,
    ) -> int:
        """Fan an event out to a room.  Dead sockets are pruned afterwards."""
        targets = [
            c
            for c in list(self._rooms.get(game_pin, {}).values())
            if (include_hosts or not c.is_host)
            and (exclude_player_id is None or c.player_id != exclude_player_id)
        ]
        if not targets:
            return 0
        results = await asyncio.gather(
            *(self.send(c, event_type, payload) for c in targets),
            return_exceptions=True,
        )
        delivered = 0
        for connection, ok in zip(targets, results):
            if ok is True:
                delivered += 1
            else:
                await self.unregister(connection)
        return delivered

    async def send_to_player(
        self, player_id: int, event_type: WSEventType | str, payload: dict[str, Any] | None = None
    ) -> bool:
        connection = self._players.get(player_id)
        if connection is None:
            return False
        if await self.send(connection, event_type, payload):
            return True
        await self.unregister(connection)
        return False

    async def send_to_hosts(
        self, game_pin: str, event_type: WSEventType | str, payload: dict[str, Any] | None = None
    ) -> int:
        targets = self.host_connections(game_pin)
        results = await asyncio.gather(
            *(self.send(c, event_type, payload) for c in targets), return_exceptions=True
        )
        delivered = 0
        for connection, ok in zip(targets, results):
            if ok is True:
                delivered += 1
            else:
                await self.unregister(connection)
        return delivered


#: Process-wide singleton, wired into the engine and the WebSocket route.
manager = ConnectionManager()
