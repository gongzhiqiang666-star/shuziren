"""Queue-backed worker for the packaged Kuaishou relay."""

import asyncio
import random
import string

from urllib.parse import quote

from .KsLive import KuaishouLiveClient, fetch_gift_info_global, get_live_info_from_url


def generate_random_secret():
    return "".join(random.choices(string.ascii_letters + string.digits, k=8))


class RoomInfoUnavailable(RuntimeError):
    pass


async def kuaishou_worker(room_id, msg_queue):
    class ForwardClient(KuaishouLiveClient):
        async def _forward_message(self, json_data):
            await msg_queue.put(json_data)

    live_url = "https://live.kuaishou.com/u/" + quote(str(room_id), safe="")
    live_info = await get_live_info_from_url(live_url)
    if not live_info:
        raise RoomInfoUnavailable("Kuaishou room connection information unavailable")
    client = ForwardClient(room_id=room_id, **live_info)
    try:
        await fetch_gift_info_global()
    except (OSError, ValueError):
        pass
    await client.start()


async def handle_authorized_connection(websocket, room_id):
    queue = asyncio.Queue()
    finished = object()

    async def collect():
        await kuaishou_worker(room_id, queue)
        await queue.put(finished)

    async def forward():
        while True:
            message = await queue.get()
            if message is finished:
                return
            await websocket.send(message)

    worker = asyncio.create_task(collect())
    sender = asyncio.create_task(forward())
    closed = asyncio.create_task(websocket.wait_closed())
    tasks = (worker, sender, closed)
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
        if worker in done and sender not in done and closed not in done:
            done, _ = await asyncio.wait((sender, closed), return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
    except RoomInfoUnavailable:
        await websocket.send('{"type":"error","msg":"获取快手房间信息失败"}')
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def ws_handler(websocket, path):
    room_id = path.strip("/").split("/", 1)[0]
    if not room_id:
        await websocket.send('{"type":"error","msg":"房间号不能为空"}')
        await websocket.close()
        return
    await handle_authorized_connection(websocket, room_id)


async def _main(host="127.0.0.1", port=8000):
    from websockets import serve

    async def compatible_handler(websocket, path=None):
        if path is None:
            request = getattr(websocket, "request", None)
            path = request.path if request is not None else websocket.path
        return await ws_handler(websocket, path)

    async with serve(compatible_handler, host, port) as server:
        await server.serve_forever()


async def main():
    return await _main()


if __name__ == "__main__":
    asyncio.run(main())
