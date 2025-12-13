#ifndef _WEBSOCKET_PROTOCOL_H_
#define _WEBSOCKET_PROTOCOL_H_


#include "protocol.h"

#include <web_socket.h>
#include <freertos/FreeRTOS.h>
#include <freertos/event_groups.h>

#define WEBSOCKET_PROTOCOL_SERVER_HELLO_EVENT (1 << 0)

class WebsocketProtocol : public Protocol {
public:
    WebsocketProtocol();
    ~WebsocketProtocol();

    bool Start() override;
    bool SendAudio(std::unique_ptr<AudioStreamPacket> packet) override;
    bool OpenAudioChannel() override;
    void CloseAudioChannel() override;
    bool IsAudioChannelOpened() const override;
    bool SendText(const std::string& text) override;
    // my code here
    bool SendVideo(const uint8_t* data, size_t len, uint32_t timestamp) override;
    void SendPlaybackTimestamp(uint64_t timestamp) override;
    
    static void websocket_sender_task_wrapper(void* pvParameters);


private:
    EventGroupHandle_t event_group_handle_;
    std::unique_ptr<WebSocket> websocket_;
    int version_ = 2;    //here change 1 to 2
    QueueHandle_t feedback_queue_;

    void ParseServerHello(const cJSON* root);
    void websocket_sender_task_impl();
    std::string GetHelloMessage();
};


#endif
