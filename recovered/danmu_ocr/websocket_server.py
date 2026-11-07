"""Protocol callbacks recovered from the OCR WebSocket server."""

import json

HEARTBEAT = '{"type":"heartbeat"}'
HEARTBEAT_ACK = '{"type":"heartbeat_ack"}'


def message_received(client, server, message):
    if message == HEARTBEAT:
        server.send_message(client, HEARTBEAT_ACK)


_EVENT_TYPES = {"danmu": 1, "like": 2, "enter": 3, "follow": 4, "gift": 5, "share": 8}


def convert_type(message_type):
    return _EVENT_TYPES.get(message_type, 0)


def format_message(message):
    return {
        "Type": convert_type(message.get("type", "danmu")),
        "Data": {
            "User": {"Nickname": message.get("username") or message.get("nickname") or "用户"},
            "Content": message.get("content") or message.get("text") or "",
        },
    }


class WebSocketServer:
    def __init__(self, port=8888):
        self.port = port
        self.server = None

    def start(self):
        if self.server is not None:
            return
        from websocket_server import WebsocketServer

        server = WebsocketServer(host="127.0.0.1", port=self.port)
        try:
            server.set_fn_new_client(self.new_client)
            server.set_fn_client_left(self.client_left)
            server.set_fn_message_received(self.message_received)
            server.run_forever(threaded=True)
        except BaseException:
            server.server_close()
            raise
        self.server = server

    def stop(self):
        server = self.server
        if server is not None:
            self.server = None
            server.shutdown_gracefully()

    def send_message(self, message):
        if self.server is not None:
            payload = json.dumps(format_message(message))
            self.server.send_message_to_all(payload)

    def new_client(self, client, server):
        return None

    def client_left(self, client, server):
        return None

    def message_received(self, client, server, message):
        return message_received(client, server, message)

    def _convert_type(self, msg_type):
        return convert_type(msg_type)

    def _format_message(self, message):
        return format_message(message)
