"""Recovered PortAudio device enumeration helper."""

from __future__ import annotations


def get_audio_devices() -> dict:
    """Enumerate the first PortAudio host API, matching the native extension."""
    import pyaudio

    devices = {"input": [], "output": []}
    player = None
    try:
        player = pyaudio.PyAudio()
        host = player.get_host_api_info_by_index(0)
        for host_device_index in range(int(host.get("deviceCount") or 0)):
            try:
                info = player.get_device_info_by_host_api_device_index(0, host_device_index)
            except Exception as error:
                print(f"枚举音频设备 {host_device_index} 失败: {error}")
                continue
            device_index = int(info.get("index", host_device_index))
            if info.get("maxInputChannels") > 0:
                devices["input"].append({"index": device_index, "name": info.get("name")})
            if info.get("maxOutputChannels") > 0:
                devices["output"].append({"index": device_index, "name": info.get("name")})
    except Exception as error:
        print("枚举音频设备失败: " + str(error))
    finally:
        if player is not None:
            player.terminate()
    return devices
