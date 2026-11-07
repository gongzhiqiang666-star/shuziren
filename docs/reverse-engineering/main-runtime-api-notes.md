# Main runtime and configuration API recovery

## 商品话术生成

`Api.generate_script` 的包装体/主体为 `0x180036950/0x180037230`，其生成器
闭包包装体/主体为 `0x180036d00/0x180036ec0`。原生签名严格接收
`product_info: dict` 和 `special_instructions: str = ""`，并不是旧恢复版支持的
列表批处理协议。

主体按字典插入顺序遍历商品，仅处理含 `content` 键的值；每项调用
`generate_structured_speech(product["content"], special_instructions)`。非空结果加入
话术列表；假值或异常都写入空话术并把字符串化的商品 ID 加入
`failed_products`，但不会中断后续商品。最终话术以两个换行符连接再 `strip()`。
只有存在失败商品且所有生成结果都为空时才加入
`error="没有成功生成任何话术"`。方法级异常返回空话术、空失败列表和
`生成脚本时发生错误：<异常>`。恢复源码、逐项失败/异常、跳过无 `content`
商品、全部失败和外层异常均已加入回归；完整门禁保持 `128/128 PASS`。

Recovered in this pass:

- User/private configuration delegation, atomic YAML persistence and recursive
  merge support.
- Token, administrator ID, OEM branding, background image and version APIs.
- Local image/voice/pretrained model enumeration and path-safe deletion.
- Audio-directory counting and bounded cache cleanup.
- Camera enumeration, resolution probing, GPU/CUDA/VRAM reporting and RTX 50
  series recognition.
- ffprobe video dimension/FPS validation with the packaged 25 FPS rule.
- Volcengine image configuration, structured script generation, chunked LLM
  translation, stream URLs and interruption state updates.
- Distribution root and `env`/`env_50` selection, FFMPEG_HOME/PATH/DLL setup,
  startup admin ID and console-output setup.
- Generic YAML/text/subprocess/media-preview helpers used by the main API.

Verification included isolated user configuration, fake OEM/assets, safe model
deletion, real 25/30 FPS sample videos, simulated camera devices, simulated RTX
5090 `nvidia-smi`, mocked LLM calls and a real AVI-to-browser-MP4 conversion.
The full recovered source tree continues to pass `compileall`.
