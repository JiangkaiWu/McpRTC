# 👁️ McpRTC


![Platform](https://img.shields.io/badge/Platform-ESP32-blue) ![Protocol](https://img.shields.io/badge/Protocol-MCP-purple) ![Stream](https://img.shields.io/badge/Stream-WebRTC-red) ![License](https://img.shields.io/badge/License-MIT-green)

**给大模型一双眼睛：通过 MCP协议 让 LLM 自主控制 WebRTC视频流的 Demo 实现。**

> **Giving Eyes to LLMs.** A bridge between Model Context Protocol and ESP32 WebRTC streams.

## 📖 简介 (Introduction)

**MCPRTC** 是一个基于 [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) 的实验性项目。

音视频流的持续传输会给 IoT 设备带来**不可忽视的能耗、带宽问题**。**MCPRTC** 允许视觉大模型（如 Gemini）根据对话上下文，**自主决定**何时开启 WebRTC 视频流并分析画面，实现了回复延迟与带宽能耗之间的平衡。

本项目基于优秀的开源硬件项目 **Xiaozhi (小智)** 进行深度改造，将 ESP32 提供的 WebRTC 库移植到小智平台，并首创性地将 WebRTC 的控制工具函数通过 MCP 协议提供给大模型，从而实现视觉感知的自主控制。

**Demo**



**✨ 核心特性：**
- 🤖 **AI 自主权**：LLM 可以调用 `start_rtc_stream` `stop_rtc_stream` 等工具主动控制视频流的开关
- 📹 **低延迟传输**：基于 WebRTC 的实时视频流传输。
- 🔋 **能耗友好**：通过按需开启摄像头，极大降低视频流传输带来的能耗，延长使用时间。
- 🔊 **保留原功能**：完全兼容小智原有的语音对话功能。


## 📦 使用方法 (Usage)
⚠️ **注意**：本项目作为实验性项目，目前仅支持立创开发版实战派S3作为硬件平台，后续会适配更多平台。
**1、固件环境安装**：ESP-IDF v5.5.0 或更高版本，具体可参考 [xiaozhi编译环境安装教程](https://icnynnzcwou8.feishu.cn/wiki/JEYDwTTALi5s2zkGlFGcDiRknXf)
**2、编译与烧录**:
首先，克隆本项目到本地：
```bash
git clone https://github.com/12345
```
然后，**打开ESP-IDF Powershell**，进入项目目录并编译固件
```bash
cd MCPRTC/xiaozhi-esp32-board
idf.py set-target esp32s3
idf.py build
```
最后，将编译好的固件烧录到 ESP32 设备上：
```bash
idf.py build flash monitor
```
**3、服务端配置**：请参考 [xiaozhi-esp32-server](https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/main/docs/Deployment_all.md#%E6%96%B9%E5%BC%8F%E4%BA%8C%E6%9C%AC%E5%9C%B0%E6%BA%90%E7%A0%81%E8%BF%90%E8%A1%8C%E5%85%A8%E6%A8%A1%E5%9D%97) 项目进行服务端配置。对应的文件在 ``MCPRTC/xiaozhi-esp32-server`` 目录下
由于原项目架构为ASR+LLM+TTS，为了将LLM替换为可以接收视频的VLLM，我对项目进行了部分修改，因此目前暂时仅支持原项目的 **方式二：本地源码运行全模块** 部署。

⚠️部署后，需要在智控台将LLM改为gemini，并将意图识别改为函数调用意图识别，如果需要代理，请把代理开启在7890端口

**4、运行项目**：启动服务端，并确保 ESP32 设备与服务器之间的网络连接正常，即可开始与模型对话

## 💡补充说明 (Additional Notes)

除自主控制视频流的开启与关闭之外，**MCPRTC** 还在框架层面支持动态调整视频流的**码率、帧率**等参数，以适应不同场景要求。考虑到硬件性能限制，目前仅保留了初步实现的工具接口，更完善的实现有待补充。

 
## 🏗️ 架构与致谢 (Architecture & Credits)

本项目站在了巨人的肩膀上。核心代码基于以下两个仓库进行了二次开发：

* **Firmware**: [xiaozhi-esp32](https://github.com/78/xiaozhi-esp32) - 提供了基于ESP32的AI智能助手原型
* **Server**: 基于 [xiaozhi-esp32-server](https://github.com/xinnan-tech/xiaozhi-esp32-server) - 提供了适配xiaozhi-esp32的服务端实现

