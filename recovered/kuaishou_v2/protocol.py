"""Decode the Kuaishou socket envelope and supported server payloads."""

import gzip

try:
    from .protobuf import kuaishou_QY_pb2 as proto
except ModuleNotFoundError:
    from . import miniproto as proto


_PAYLOAD_CLASSES = {
    proto.SC_ENTER_ROOM_ACK: proto.SCWebEnterRoomAck,
    proto.SC_FEED_PUSH: proto.SCWebFeedPush,
}
if hasattr(proto,"SC_LIVE_WATCHING_LIST") and hasattr(proto,"SCWebLiveWatchingUsers"):
    _PAYLOAD_CLASSES[proto.SC_LIVE_WATCHING_LIST]=proto.SCWebLiveWatchingUsers


def decode_frame(data: bytes):
    envelope = proto.SocketMessage.FromString(data)
    message_class = _PAYLOAD_CLASSES.get(envelope.payloadType)
    if message_class is None:
        return envelope.payloadType, envelope.payload

    payload = envelope.payload
    if envelope.compressionType == proto.SocketMessage.GZIP:
        payload = gzip.decompress(payload)
    elif envelope.compressionType not in (proto.SocketMessage.UNKNOWN, proto.SocketMessage.NONE):
        raise ValueError(f"Unsupported Kuaishou payload encoding {envelope.compressionType}")
    return envelope.payloadType, message_class.FromString(payload)


def _encode_frame(payload_type: int, payload) -> bytes:
    return proto.SocketMessage(
        payloadType=payload_type,
        compressionType=proto.SocketMessage.NONE,
        payload=payload.SerializeToString(),
    ).SerializeToString()


def encode_enter_room(live_stream_id: str, token: str, page_id: str) -> bytes:
    return _encode_frame(
        proto.CS_ENTER_ROOM,
        proto.CSWebEnterRoom(liveStreamId=live_stream_id, token=token, pageId=page_id),
    )


def encode_heartbeat(timestamp_ms: int) -> bytes:
    return _encode_frame(proto.CS_HEARTBEAT, proto.CSWebHeartbeat(timestamp=timestamp_ms))


def iter_comments(feed):
    """Adapt a decoded feed to the recovered live manager's comment fields."""
    for comment in feed.commentFeeds:
        yield {
            "type": "chat",
            "user_name": comment.user.userName,
            "user_id": comment.user.principalId,
            "avatar": getattr(comment.user,"headUrl",""),
            "content": comment.content,
        }


def iter_likes(feed):
    for like in feed.likeFeeds:
        yield {
            "type": "like",
            "user_name": like.user.userName,
            "user_id": like.user.principalId,
            "avatar": getattr(like.user,"headUrl",""),
        }


def iter_gifts(feed):
    for gift in feed.giftFeeds:
        yield {
            "type": "gift",
            "user_name": gift.user.userName,
            "user_id": gift.user.principalId,
            "avatar": getattr(gift.user,"headUrl",""),
            "gift_id": gift.giftId,
            "gift_count": gift.comboCount or gift.batchSize or 1,
        }
