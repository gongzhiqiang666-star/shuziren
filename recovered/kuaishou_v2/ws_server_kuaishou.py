import asyncio
import json
import sys
import argparse
import websockets
from .KsLive import KuaishouLiveClient, get_live_info_from_url, fetch_gift_info_global

# Set of connected WebSocket clients
connected_clients = set()

class BroadcastingClient(KuaishouLiveClient):
    """
    A Kuaishou client that broadcasts messages to local WebSocket clients.
    """
    async def _forward_message(self, json_data):
        """
        Override _forward_message to broadcast to connected local clients.
        """
        # Parse JSON to ensure it's valid, or just forward string
        try:
            # Broadcast to all connected clients
            if connected_clients:
                # websockets.broadcast expects an iterable of websockets
                websockets.broadcast(connected_clients, json_data)
                # print(f"Broadcasted: {json_data[:100]}...")
        except Exception as e:
            print(f"Error broadcasting message: {e}")

async def handler(websocket):
    """
    Handle incoming WebSocket connections from local clients (e.g. ws_capture.py).
    """
    connected_clients.add(websocket)
    print(f"New client connected. Total clients: {len(connected_clients)}")
    try:
        await websocket.wait_closed()
    finally:
        connected_clients.remove(websocket)
        print(f"Client disconnected. Total clients: {len(connected_clients)}")

async def start_kuaishou_client(live_url):
    """
    Start the Kuaishou client logic.
    """
    print("Fetching global gift info...")
    try:
        await fetch_gift_info_global()
    except (OSError, ValueError) as error:
        print(f"Gift catalog unavailable: {error}")

    room_id = live_url.split('/')[-1]
    print(f"Connecting to Kuaishou room: {room_id}")
    
    live_info = await get_live_info_from_url(live_url)
    
    if live_info:
        client = BroadcastingClient(
            live_stream_id=live_info["live_stream_id"],
            token=live_info["token"],
            ws_url=live_info["ws_url"],
            room_id=room_id
        )
        await client.start()
    else:
        raise RuntimeError(f"Failed to get live info for {room_id}")

async def main():
    parser = argparse.ArgumentParser(description='Kuaishou Live Danmu Capture Server')
    parser.add_argument('url', help='Kuaishou Live URL')
    args = parser.parse_args()

    # Start the WebSocket server on port 8888
    print("Starting local WebSocket server on port 8888...")
    async with websockets.serve(handler, "127.0.0.1", 8888):
        await start_kuaishou_client(args.url)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Server stopped by user")

