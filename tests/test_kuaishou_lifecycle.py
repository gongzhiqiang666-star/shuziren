import asyncio
from contextlib import redirect_stdout
import io
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from recovered.kuaishou_v2.KsLive import KuaishouLiveClient


class _Socket:
    def __init__(self):
        self.sent = []

    async def send(self, value):
        self.sent.append(value)


class KuaishouLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def client(self):
        return KuaishouLiveClient("stream", "token", "wss://example")

    async def test_server_heartbeat_interval_is_used(self):
        client = self.client()
        client.heartbeat_interval_ms = 3500
        waits = []

        async def stop_after_first_wait(delay):
            waits.append(delay)
            raise asyncio.CancelledError

        original_sleep = asyncio.sleep
        asyncio.sleep = stop_after_first_wait
        try:
            with self.assertRaises(asyncio.CancelledError):
                await client._send_heartbeat(_Socket())
        finally:
            asyncio.sleep = original_sleep

        self.assertEqual(waits, [3.5])

    async def test_message_completion_cancels_heartbeat_task(self):
        client = self.client()
        heartbeat_started = asyncio.Event()
        heartbeat_cancelled = asyncio.Event()

        async def heartbeat(_socket):
            heartbeat_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                heartbeat_cancelled.set()

        async def messages(_socket):
            await heartbeat_started.wait()

        client._send_heartbeat = heartbeat
        client._on_message = messages
        socket = _Socket()
        await asyncio.wait_for(client._on_open(socket), timeout=1)

        self.assertTrue(heartbeat_cancelled.is_set())
        self.assertEqual(socket.sent, [bytes.fromhex(client.encoded_data)])

    async def test_heartbeat_failure_cancels_message_task(self):
        client = self.client()
        message_started = asyncio.Event()
        message_cancelled = asyncio.Event()

        async def heartbeat(_socket):
            await message_started.wait()
            raise RuntimeError("heartbeat failed")

        async def messages(_socket):
            message_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                message_cancelled.set()

        client._send_heartbeat = heartbeat
        client._on_message = messages
        await asyncio.wait_for(client._on_open(_Socket()), timeout=1)

        self.assertTrue(message_cancelled.is_set())

    async def test_connect_retries_failure_and_normal_disconnect(self):
        client = self.client()
        outcomes = iter(("failure", "success", "cancel"))
        connect_calls = []
        waits = []

        class Connection:
            async def __aenter__(self):
                outcome = next(outcomes)
                if outcome == "failure":
                    raise OSError("private upstream error")
                if outcome == "cancel":
                    raise asyncio.CancelledError
                return _Socket()

            async def __aexit__(self, *_args):
                return False

        def connect(*args, **kwargs):
            connect_calls.append((args, kwargs))
            return Connection()

        async def on_open(_socket):
            return None

        async def sleep(delay):
            waits.append(delay)

        client._on_open = on_open
        client._calculate_reconnect_delay = lambda: 0.25
        output = io.StringIO()
        fake_websockets = SimpleNamespace(connect=connect)
        with patch.dict(sys.modules, {"websockets": fake_websockets}), patch(
                "recovered.kuaishou_v2.KsLive.asyncio.sleep", new=sleep), redirect_stdout(output):
            with self.assertRaises(asyncio.CancelledError):
                await client._connect()

        self.assertEqual(len(connect_calls), 3)
        self.assertEqual(waits, [0.25, 0.25])
        self.assertNotIn("private upstream error", output.getvalue())
        self.assertEqual(connect_calls[0][1]["close_timeout"], 10)


if __name__ == "__main__":
    unittest.main()
