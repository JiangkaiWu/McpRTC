from plugins_func.register import register_function, ToolType, ActionResponse, Action
import subprocess
import asyncio

start_webrtc_func_description = {
    "type": "function",
    "function": {
        "name": "start_webrtc",
        "description": ("重要：此工具只能在WebRTC连接状态为False的时候调用。"
                        "能够建立一段实时的音视频连接，用于和用户进行实时的音视频通话"
                        "当用户需要进行视频通话，或者需要看到用户周边的环境时，可以调用此工具"
                        "调用此工具后，系统会自动启动一个WebRTC客户端，连接到预设的WebRTC服务器"
                        "用户和系统之间的音视频数据会通过该连接进行传输"),
        "parameters": {
            "type": "object",
            "properties": {},  #  <-- 关键点：设置为空对象
            "required": []    #  <-- 关键点：设置为空数组
        }
    }
}

@register_function("start_webrtc", start_webrtc_func_description, ToolType.SYSTEM_CTL)
def start_webrtc(conn):
    """
    启动 WebRTC客户端，建立WebRTC连接
    """
    print("启动webrtc客户端")
    asyncio.create_task(conn.webrtc_client.run())
    conn.webrtc_connection_established = True
    conn.webrtc_stream_open = True
    
    return ActionResponse(
        action=Action.REQLLM,
        result ="已经启动 WebRTC 客户端，建立 WebRTC连接， 建立成功后即可接收用户录制的视频了",
        response=None
    )