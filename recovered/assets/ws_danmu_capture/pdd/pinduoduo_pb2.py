"""Self-contained protobuf wire implementation for ``pdd.proto``."""
from __future__ import annotations

def _varint(value):
    out = bytearray()
    while value > 127: out.append((value & 127) | 128); value >>= 7
    out.append(value); return bytes(out)

def _read_varint(data, pos):
    value = shift = 0
    while pos < len(data):
        byte = data[pos]; pos += 1; value |= (byte & 127) << shift
        if not byte & 128: return value, pos
        shift += 7
        if shift > 70: raise ValueError("invalid protobuf varint")
    raise ValueError("truncated protobuf varint")

class _Message:
    FIELDS = {}; FIELD_NAMES = ()
    def __init__(self, **values):
        for name, (_, _, default) in self.FIELDS.items(): setattr(self, name, values.pop(name, default))
        if values: raise TypeError(f"unknown fields: {', '.join(values)}")
    def ParseFromString(self, data):
        pos = 0; by_number = {spec[0]: (name, spec) for name, spec in self.FIELDS.items()}
        while pos < len(data):
            tag, pos = _read_varint(data, pos); number, wire = tag >> 3, tag & 7
            target = by_number.get(number)
            if wire == 0: value, pos = _read_varint(data, pos)
            elif wire == 2:
                size, pos = _read_varint(data, pos); value = data[pos:pos + size]; pos += size
                if len(value) != size: raise ValueError("truncated protobuf field")
            elif wire == 1: value, pos = data[pos:pos + 8], pos + 8
            elif wire == 5: value, pos = data[pos:pos + 4], pos + 4
            else: raise ValueError(f"unsupported protobuf wire type {wire}")
            if target:
                name, (_, kind, _) = target
                if kind == "string": value = value.decode("utf-8")
                elif kind == "bool": value = bool(value)
                setattr(self, name, value)
        return len(data)
    @classmethod
    def FromString(cls, data):
        message = cls(); message.ParseFromString(data); return message
    def SerializeToString(self):
        out = bytearray()
        for name, (number, kind, default) in self.FIELDS.items():
            value = getattr(self, name)
            if value == default: continue
            if kind in ("uint32", "uint64", "bool"):
                out += _varint(number << 3); out += _varint(int(value))
            else:
                raw = value.encode() if kind == "string" else bytes(value)
                out += _varint((number << 3) | 2); out += _varint(len(raw)); out += raw
        return bytes(out)

class Command(_Message):
    FIELDS = {
        "command": (1,"string",""), "protocol": (2,"uint32",0), "errorCode": (3,"uint32",0),
        "bizCode": (4,"uint32",0), "bizErrorMsg": (5,"string",""), "compress": (6,"uint32",0),
        "extension": (9,"bytes",b""), "body": (10,"bytes",b""), "downstreamSeq": (11,"uint64",0),
        "conId": (12,"uint64",0), "ctxId": (13,"uint64",0),
    }
    FIELD_NAMES = tuple(FIELDS)

class Body(_Message):
    FIELDS = {"bizType": (1,"uint32",0), "groupId": (2,"string",""), "msgId": (3,"string",""),
              "payload": (4,"string",""), "needAck": (5,"bool",False)}
    FIELD_NAMES = tuple(FIELDS)
