import asyncio
import unittest

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


if __name__ == "__main__":
    unittest.main()
