import asyncio
import json
import logging
import random
import string
import argparse

import requests
import websockets
import argparse
import multiprocessing
import numpy as np
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate, RTCConfiguration, RTCIceServer
from aiortc.contrib.media import MediaPlayer,MediaRecorder
from aiortc.sdp import candidate_from_sdp

# Set up logging to see the flow of messages
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("apprtc")

# The public AppRTC server
APPRTC_URL = "https://webrtc.espressif.com"
ESP_PEER_SIGNALING_MSG_CUSTOMIZED = 4

def generate_random_room_id(length=9):
    """Generate a random string of numbers for the room ID."""
    return "".join(random.choice(string.digits) for _ in range(length))

def make_compatible_sdp(sdp: str) -> str:
    # 把 High Profile 改为 Baseline，让 aiortc 接受 SDP
    sdp = sdp.replace("profile-level-id=4d001f", "profile-level-id=42e01f")
    return sdp

class AppRTCClient:
    """
    Main class to handle the AppRTC signaling and WebRTC connection.
    """
    def __init__(self, need_close, ipc_queue: multiprocessing.Queue):
        self.need_close = need_close
        self.room_id = "831143513"
        self.client_id = None
        self.is_initiator = False
        self.pc = None  # Will be created in connect()
        self.websocket = None
        self.base_url = None
        self.wss_url = None
        self.wss_post_url = None
        
        # self.player = MediaPlayer('testsrc', format='lavfi', options={'video_size': '640x480'})
        self.recorder = None
    async def on_icecandidate(self, candidate):
        if candidate:
            logger.info(f"Generated ICE Candidate: {candidate.candidate}")
            await self.send_candidate(candidate)

    def on_track(self, track):
        logger.info(f"Track {track.kind} received")

        if track.kind == "video":
            # --- [关键修改] 用 try...except 包裹整个录制器逻辑 ---
            try:
                if self.recorder is None:
                    logger.info("Attempting to create MediaRecorder for 'received_video.mp4'...")
                    
                    # 再次打印工作目录，确认路径是否正确
                    import os
                    logger.info(f"Current working directory (CWD) is: {os.getcwd()}")
                    
                    # 尝试创建对象
                    self.recorder = MediaRecorder("received_video.mp4")
                    logger.info("SUCCESS: MediaRecorder object created.")
                    
                    # 尝试添加轨道
                    self.recorder.addTrack(track)
                    logger.info("SUCCESS: Track added to recorder.")
                    
                    # 尝试启动后台录制任务
                    logger.info("Attempting to start recorder task...")
                    asyncio.create_task(self.recorder.start())
                    logger.info("SUCCESS: Recorder task created and scheduled.")

            except Exception as e:
                # 这一段日志至关重要！
                logger.error("!!!!!!!! CRITICAL FAILURE in on_track !!!!!!!!")
                logger.error(f"Error creating or starting MediaRecorder: {e}", exc_info=True)
                # exc_info=True 会打印完整的错误堆栈跟踪信息

            # 注意：原有的 @track.on("ended") 逻辑保持不变，仍在 on_track 方法内部
            @track.on("ended")
            async def on_ended():
                logger.info(f"Track {track.kind} ended")
                if self.recorder:
                    await self.recorder.stop()
    async def connect(self):
        """
        Join the room, get ICE servers, and then create the PeerConnection.
        """
        join_url = f"{APPRTC_URL}/join/{self.room_id}"
        logger.info(f"Joining room: {join_url}")
        
        try:
            response = requests.post(join_url)
            response.raise_for_status()
            data = response.json()
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            logger.error(f"Failed to join room: {e}")
            return False

        print(data)
        params = data.get("params", {})
        self.client_id = params.get("client_id")
        self.is_initiator = params.get("is_initiator") == "true"
        self.wss_url = params.get("wss_url")
        self.wss_post_url = params.get("wss_post_url")
        self.base_url = APPRTC_URL
        
        logger.info(f"Joined room {self.room_id} as client {self.client_id}")
        logger.info(f"I am the initiator: {self.is_initiator}")
        
        # Get ICE servers
        ice_servers = []
        ice_server_url = params.get("ice_server_url")
        if ice_server_url:
            logger.info("Fetching ICE servers...")
            try:
                ice_response = requests.post(ice_server_url)
                ice_response.raise_for_status()
                ice_servers_json = ice_response.json().get("iceServers", [])
                
                for s in ice_servers_json:
                    # 支持 urls 为单个字符串或列表
                    urls = s.get("urls")
                    username = s.get("username")
                    credential = s.get("credential")

                    ice_server = RTCIceServer(urls=urls, username=username, credential=credential)
                    ice_servers.append(ice_server)
                logger.info(f"Using {len(ice_servers)} ICE servers.")
            except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
                    logger.warning(f"Failed to get ICE servers, continuing without them: {e}")


        # Create RTCConfiguration and RTCPeerConnection
        config = RTCConfiguration(iceServers=ice_servers)
        self.pc = RTCPeerConnection(configuration=config)
        
        # Register event handlers
        self.pc.on("icecandidate", self.on_icecandidate)
        self.pc.on("track", self.on_track)
        
        # Connect to the WebSocket signaling server
        logger.info(f"Connecting to WebSocket: {self.wss_url}")
        headers = {"Origin": self.base_url}
        self.websocket = await websockets.connect(
            self.wss_url,
            additional_headers=headers)
        
        # Process any initial messages
        initial_messages = params.get("messages", [])
        for msg_str in initial_messages:
            await self.handle_message(msg_str)
            
        return True

    async def run(self):
        if not await self.connect():
            return
            
        register_msg = {
            "cmd": "register",
            "roomid": self.room_id,
            "clientid": self.client_id
        }
        await self.websocket.send(json.dumps(register_msg))
        logger.info("Registered with signaling server.")
        
        if not self.is_initiator:
            ringing_msg = {
                "cmd": "send",
                "msg": json.dumps({"type": "customized", "data": "RING"}),
            }
            await self.websocket.send(json.dumps(ringing_msg))
            logger.info("Not initialor, Sent RING message.")

        try:
            async for message in self.websocket:
                await self.handle_message(message)
        except websockets.exceptions.ConnectionClosed as e:
            logger.info(f"WebSocket connection closed: {e}")
        finally:
            await self.close()
            
    async def handle_message(self, message_str):
        try:
            data = json.loads(message_str)
            msg_content_str = data.get("msg")
            if not msg_content_str:
                logger.warning(f"Received message without 'msg' field: {data}")
                msg = data
            else:
                msg = json.loads(msg_content_str)
            msg_type = msg.get("type")
            
            logger.info(f"Received message of type: {msg_type}")

            if msg_type == "offer":
                offer = RTCSessionDescription(sdp=make_compatible_sdp(msg["sdp"]), type=msg["type"])
                await self.pc.setRemoteDescription(offer)
                
                logger.info("Creating SDP answer...")
                # self.pc.addTrack(self.player.video)
                answer = await self.pc.createAnswer()
                await self.pc.setLocalDescription(answer)
                await self.send_sdp(self.pc.localDescription)
            elif msg_type == "answer":
                answer = RTCSessionDescription(sdp=make_compatible_sdp(msg["sdp"]), type=msg["type"])

                await self.pc.setRemoteDescription(answer)
            elif msg_type == "candidate":
                candidate = candidate_from_sdp(msg["candidate"])
                candidate.sdpMid = msg["id"]
                candidate.sdpMLineIndex = msg["label"]
                await self.pc.addIceCandidate(candidate)

            elif msg_type == "customized":
                message_data = msg.get("data", "")
                if message_data == "RING":
                    accept_msg = {
                        "cmd": "send",
                        "msg": json.dumps({"type": "customized", "data": "ACCEPT_CALL"}),
                    }
                    await self.websocket.send(json.dumps(accept_msg))
                    logger.info("Received RING message from peer.Send Accept")

                    logger.info("Creating SDP offer...")
                    # self.pc.addTrack(self.player.video)
                    
                    offer = await self.pc.createOffer()
                    compatible_sdp = make_compatible_sdp(offer.sdp)
                    offer = RTCSessionDescription(sdp=compatible_sdp, type=offer.type)
                    await self.pc.setLocalDescription(offer)
                    await self.send_sdp(self.pc.localDescription)

                elif message_data == "ACCEPT_CALL":

                    logger.info("Received ACCEPT_CALL message from peer.")
                logger.info(f"Received customized data: {message_data}")

            elif msg_type == "bye":
                logger.info("Peer has left the room. Closing connection.")
                await self.close()
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Could not parse message: {message_str}, error: {e}")
            
    async def send_sdp(self, description):
        message = {"sdp": description.sdp, "type": description.type}
        post_url = f"{self.base_url}/message/{self.room_id}/{self.client_id}"
        logger.info(f"Sending {description.type} to {post_url}")
        try:
            requests.post(post_url, json=message).raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send SDP: {e}")
            
    async def send_candidate(self, candidate):
        message = {
            "type": "candidate",
            "candidate": candidate.to_sdp(),
            "id": candidate.sdpMid,
            "label": candidate.sdpMLineIndex
        }
        post_url = f"{self.base_url}/message/{self.room_id}/{self.client_id}"
        logger.info(f"Sending ICE candidate to {post_url}")
        try:
            requests.post(post_url, json=message).raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send ICE candidate: {e}")


    async def close(self):
        if self.pc and self.pc.connectionState != "closed":
            # 如果需要对方退出
            if self.need_close: 
                close_msg = {
                    "cmd": "send",
                    "msg": json.dumps({"type": "customized" , "data": "CLOSE"})
                }
                await self.websocket.send(json.dumps(close_msg))
                logger.info("Send Close Message.")
            # 如果不需对方退出，自己退出即可
            else:
                # send bye first
                bye_msg = {
                    "cmd": "send",
                    "msg": json.dumps({"type": "bye"}),
                }
                await self.websocket.send(json.dumps(bye_msg))
                logger.info("Send Bye Message.")
            logger.info("Closing RTCPeerConnection")
            await self.pc.close()
        # Stop the recorder first if it's running
        if self.recorder:
            logger.info("Stopping recorder...")
            try:
                await self.recorder.stop()
                # --- ADD THIS LOG ---
                print("Script finished.")
                logger.info("SUCCESS: Recorder stopped cleanly.")
            except Exception as e:
                logger.error(f"!!!!!!!! FAILED TO STOP RECORDER: {e}")
            self.recorder = None
        if self.websocket and not self.websocket.close:
            logger.info("Closing WebSocket connection")
            await self.websocket.close()
        if self.client_id and self.room_id:
            leave_url = f"{self.wss_post_url}/{self.room_id}/{self.client_id}"
            logger.info(f"Sending leave message to {leave_url}")
            try:
                requests.delete(leave_url)
            except requests.exceptions.RequestException:
                pass

async def main():
    parser = argparse.ArgumentParser(description="AppRTC client in Python.")
    parser.add_argument("need_close", type=int, help="Whether notify to close the connection.")
    args = parser.parse_args()

    client = AppRTCClient(args.need_close)
    try:
        await client.run()
    except KeyboardInterrupt:
        pass
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())