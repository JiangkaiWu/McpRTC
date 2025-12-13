#include "websocket_protocol.h"
#include "board.h"
#include "system_info.h"
#include "application.h"
#include "settings.h"

#include <cstring>
#include <cJSON.h>
#include <esp_log.h>
#include <arpa/inet.h>
#include <endian.h>
#include "assets/lang_config.h"



#define TAG "WS"

// 定义要通过队列传递的消息
// 只需要原始包的时间戳就足够了
struct FeedbackRequest {
    uint64_t original_timestamp;
};



WebsocketProtocol::WebsocketProtocol() {
    event_group_handle_ = xEventGroupCreate();
    feedback_queue_ = xQueueCreate(10, sizeof(FeedbackRequest));
    if (feedback_queue_ == nullptr) {
        ESP_LOGE(TAG, "Failed to create feedback queue!");
        // 这里应该有更健壮的错误处理
    }
}

WebsocketProtocol::~WebsocketProtocol() {
    vEventGroupDelete(event_group_handle_);
    if (feedback_queue_ != nullptr) {
        vQueueDelete(feedback_queue_);
    }
}

bool WebsocketProtocol::Start() {
    // Only connect to server when audio channel is needed
    return true;
}

bool WebsocketProtocol::SendAudio(std::unique_ptr<AudioStreamPacket> packet) {
    if (websocket_ == nullptr || !websocket_->IsConnected()) {
        return false;
    }

    if (version_ == 2) {
        std::string serialized;
        serialized.resize(sizeof(BinaryProtocol2) + packet->payload.size());
        auto bp2 = (BinaryProtocol2*)serialized.data();
        bp2->version = htons(version_);
        bp2->type = 0;
        bp2->reserved = 0;
        // bp2->timestamp = htonl(packet->timestamp);

        struct timeval tv;
        // 1. 使用 gettimeofday() 获取被SNTP同步过的当前时间
        gettimeofday(&tv, NULL);
        // 2. 将秒和微秒统一转换为64位的毫秒时间戳
        uint64_t total_milliseconds = (uint64_t)tv.tv_sec * 1000000 + (uint64_t)tv.tv_usec;
        // 3. 【关键步骤】截断为低32位，并存入数据包
        bp2->timestamp = htobe64(total_milliseconds);
        
        bp2->payload_size = htonl(packet->payload.size());
        memcpy(bp2->payload, packet->payload.data(), packet->payload.size());

        return websocket_->Send(serialized.data(), serialized.size(), true);
    } else if (version_ == 3) {
        std::string serialized;
        serialized.resize(sizeof(BinaryProtocol3) + packet->payload.size());
        auto bp3 = (BinaryProtocol3*)serialized.data();
        bp3->type = 0;
        bp3->reserved = 0;
        bp3->payload_size = htons(packet->payload.size());
        memcpy(bp3->payload, packet->payload.data(), packet->payload.size());

        return websocket_->Send(serialized.data(), serialized.size(), true);
    } else {
        return websocket_->Send(packet->payload.data(), packet->payload.size(), true);
    }
}

bool WebsocketProtocol::SendText(const std::string& text) {
    if (websocket_ == nullptr || !websocket_->IsConnected()) {
        return false;
    }

    if (!websocket_->Send(text)) {
        ESP_LOGE(TAG, "Failed to send text: %s", text.c_str());
        SetError(Lang::Strings::SERVER_ERROR);
        return false;
    }

    return true;
}

bool WebsocketProtocol::IsAudioChannelOpened() const {
    return websocket_ != nullptr && websocket_->IsConnected() && !error_occurred_ && !IsTimeout();
}

void WebsocketProtocol::CloseAudioChannel() {
    websocket_.reset();
}

bool WebsocketProtocol::OpenAudioChannel() {
    Settings settings("websocket", false);
    std::string url = settings.GetString("url");
    std::string token = settings.GetString("token");
    int version = settings.GetInt("version");
    if (version != 0) {
        version_ = version;
    }

    error_occurred_ = false;

    auto network = Board::GetInstance().GetNetwork();
    websocket_ = network->CreateWebSocket(1);
    if (websocket_ == nullptr) {
        ESP_LOGE(TAG, "Failed to create websocket");
        return false;
    }

    if (!token.empty()) {
        // If token not has a space, add "Bearer " prefix
        if (token.find(" ") == std::string::npos) {
            token = "Bearer " + token;
        }
        websocket_->SetHeader("Authorization", token.c_str());
    }
    websocket_->SetHeader("Protocol-Version", std::to_string(version_).c_str());
    websocket_->SetHeader("Device-Id", SystemInfo::GetMacAddress().c_str());
    websocket_->SetHeader("Client-Id", Board::GetInstance().GetUuid().c_str());

    websocket_->OnData([this](const char* data, size_t len, bool binary) {
        if (binary) {
            if (on_incoming_audio_ != nullptr) {
                if (version_ == 2) {
                    BinaryProtocol2* bp2 = (BinaryProtocol2*)data;
                    bp2->version = ntohs(bp2->version);
                    bp2->type = ntohs(bp2->type);
                    bp2->timestamp = be64toh(bp2->timestamp);
                    bp2->payload_size = ntohl(bp2->payload_size);
                    auto payload = (uint8_t*)bp2->payload;

                    // FeedbackRequest request;
                    // request.original_timestamp = bp2->timestamp;
                    
                    // ESP_LOGI(TAG, "OnData: Received packet with timestamp %llu",bp2->timestamp);;
                    // // 4. 将请求发送到队列
                    // if (xQueueSend(this->feedback_queue_, &request, pdMS_TO_TICKS(10)) != pdTRUE) {
                    //     ESP_LOGE(TAG, "Failed to post feedback request to queue. Queue might be full.");
                    // }


                    on_incoming_audio_(std::make_unique<AudioStreamPacket>(AudioStreamPacket{
                        .sample_rate = server_sample_rate_,
                        .frame_duration = server_frame_duration_,
                        .timestamp = bp2->timestamp,
                        .payload = std::vector<uint8_t>(payload, payload + bp2->payload_size)
                    }));
                } else if (version_ == 3) {
                    BinaryProtocol3* bp3 = (BinaryProtocol3*)data;
                    bp3->type = bp3->type;
                    bp3->payload_size = ntohs(bp3->payload_size);
                    auto payload = (uint8_t*)bp3->payload;
                    on_incoming_audio_(std::make_unique<AudioStreamPacket>(AudioStreamPacket{
                        .sample_rate = server_sample_rate_,
                        .frame_duration = server_frame_duration_,
                        .timestamp = 0,
                        .payload = std::vector<uint8_t>(payload, payload + bp3->payload_size)
                    }));
                } else {
                    on_incoming_audio_(std::make_unique<AudioStreamPacket>(AudioStreamPacket{
                        .sample_rate = server_sample_rate_,
                        .frame_duration = server_frame_duration_,
                        .timestamp = 0,
                        .payload = std::vector<uint8_t>((uint8_t*)data, (uint8_t*)data + len)
                    }));
                }
            }
        } else {
            // Parse JSON data
            auto root = cJSON_Parse(data);
            auto type = cJSON_GetObjectItem(root, "type");
            if (cJSON_IsString(type)) {
                if (strcmp(type->valuestring, "hello") == 0) {
                    ParseServerHello(root);
                } else {
                    if (on_incoming_json_ != nullptr) {
                        on_incoming_json_(root);
                    }
                }
            } else {
                ESP_LOGE(TAG, "Missing message type, data: %s", data);
            }
            cJSON_Delete(root);
        }
        last_incoming_time_ = std::chrono::steady_clock::now();
    });

    websocket_->OnDisconnected([this]() {
        ESP_LOGI(TAG, "Websocket disconnected");
        if (on_audio_channel_closed_ != nullptr) {
            on_audio_channel_closed_();
        }
    });

    ESP_LOGI(TAG, "Connecting to websocket server: %s with version: %d", url.c_str(), version_);
    if (!websocket_->Connect(url.c_str())) {
        ESP_LOGE(TAG, "Failed to connect to websocket server");
        SetError(Lang::Strings::SERVER_NOT_CONNECTED);
        return false;
    }

    if (on_connected_ != nullptr) {
        on_connected_();
    }

    // Send hello message to describe the client
    auto message = GetHelloMessage();
    if (!SendText(message)) {
        return false;
    }

    // Wait for server hello
    EventBits_t bits = xEventGroupWaitBits(event_group_handle_, WEBSOCKET_PROTOCOL_SERVER_HELLO_EVENT, pdTRUE, pdFALSE, pdMS_TO_TICKS(10000));
    if (!(bits & WEBSOCKET_PROTOCOL_SERVER_HELLO_EVENT)) {
        ESP_LOGE(TAG, "Failed to receive server hello");
        SetError(Lang::Strings::SERVER_TIMEOUT);
        return false;
    }

    if (on_audio_channel_opened_ != nullptr) {
        on_audio_channel_opened_();
    }

    return true;
}

std::string WebsocketProtocol::GetHelloMessage() {
    // keys: message type, version, audio_params (format, sample_rate, channels)
    cJSON* root = cJSON_CreateObject();
    cJSON_AddStringToObject(root, "type", "hello");
    cJSON_AddNumberToObject(root, "version", version_);
    cJSON* features = cJSON_CreateObject();
#if CONFIG_USE_SERVER_AEC
    cJSON_AddBoolToObject(features, "aec", true);
#endif
    cJSON_AddBoolToObject(features, "mcp", true);
    cJSON_AddItemToObject(root, "features", features);
    cJSON_AddStringToObject(root, "transport", "websocket");
    cJSON* audio_params = cJSON_CreateObject();
    cJSON_AddStringToObject(audio_params, "format", "opus");
    cJSON_AddNumberToObject(audio_params, "sample_rate", 16000);
    cJSON_AddNumberToObject(audio_params, "channels", 1);
    cJSON_AddNumberToObject(audio_params, "frame_duration", OPUS_FRAME_DURATION_MS);
    cJSON_AddItemToObject(root, "audio_params", audio_params);
    auto json_str = cJSON_PrintUnformatted(root);
    std::string message(json_str);
    cJSON_free(json_str);
    cJSON_Delete(root);
    return message;
}

void WebsocketProtocol::ParseServerHello(const cJSON* root) {
    auto transport = cJSON_GetObjectItem(root, "transport");
    if (transport == nullptr || strcmp(transport->valuestring, "websocket") != 0) {
        ESP_LOGE(TAG, "Unsupported transport: %s", transport->valuestring);
        return;
    }

    auto session_id = cJSON_GetObjectItem(root, "session_id");
    if (cJSON_IsString(session_id)) {
        session_id_ = session_id->valuestring;
        ESP_LOGI(TAG, "Session ID: %s", session_id_.c_str());
    }

    auto audio_params = cJSON_GetObjectItem(root, "audio_params");
    if (cJSON_IsObject(audio_params)) {
        auto sample_rate = cJSON_GetObjectItem(audio_params, "sample_rate");
        if (cJSON_IsNumber(sample_rate)) {
            server_sample_rate_ = sample_rate->valueint;
        }
        auto frame_duration = cJSON_GetObjectItem(audio_params, "frame_duration");
        if (cJSON_IsNumber(frame_duration)) {
            server_frame_duration_ = frame_duration->valueint;
        }
    }

    xEventGroupSetBits(event_group_handle_, WEBSOCKET_PROTOCOL_SERVER_HELLO_EVENT);
}


// my code here
bool WebsocketProtocol::SendVideo(const uint8_t* data, size_t len, uint32_t timestamp) {
    if (websocket_ == nullptr || !websocket_->IsConnected()) {
        return false;
    }

    if (version_ == 2) {
        std::string serialized;
        serialized.resize(sizeof(BinaryProtocol2) + len);
        auto bp2 = (BinaryProtocol2*)serialized.data();
        bp2->version = htons(version_);
        bp2->type = htons(2); // 2 代表JPEG 
        bp2->reserved = 0;
        bp2->timestamp = htonl(timestamp); // 使用视频帧的时间戳
        bp2->payload_size = htonl(len);
        memcpy(bp2->payload, data, len);

        ESP_LOGI(TAG, "data ready,start sending;");
        return websocket_->Send(serialized.data(), serialized.size(), true);
    } else if (version_ == 3) {
        std::string serialized;
        serialized.resize(sizeof(BinaryProtocol3) + len);
        auto bp3 = (BinaryProtocol3*)serialized.data();
        bp3->type = 2; // 2 代表JPEG
        bp3->reserved = 0;
        bp3->payload_size = htons(len);
        memcpy(bp3->payload, data, len);

        return websocket_->Send(serialized.data(), serialized.size(), true);
    } else {
        // 对于不支持类型的旧协议，可能无法发送
        ESP_LOGW(TAG, "Protocol version %d does not support typed streams", version_);
        return false;
    }
}

void WebsocketProtocol::websocket_sender_task_wrapper(void* pvParameters) {
    WebsocketProtocol* self = static_cast<WebsocketProtocol*>(pvParameters);
    if (self) {
        self->websocket_sender_task_impl();
    }
}

void WebsocketProtocol::websocket_sender_task_impl() {
    FeedbackRequest request;

    ESP_LOGI(TAG, "Sender task started.");

    while (true) {
        // 1. 阻塞等待，直到从队列中收到一个回执请求
        if (xQueueReceive(this->feedback_queue_, &request, portMAX_DELAY)) {
            // ESP_LOGI(TAG, "Sender Task: Dequeued request with original_ts=%" PRIu64, request.original_timestamp);

            // --- 开始构建并发送 Feedback 包 ---
            std::vector<uint8_t> serialized_data;
            serialized_data.resize(sizeof(BinaryProtocol2)); // 没有 payload

            auto bp2_to_send = reinterpret_cast<BinaryProtocol2*>(serialized_data.data());

            // 填充字段并进行正确的主机到网络字节序转换
            bp2_to_send->version = htons(version_);
            bp2_to_send->type = htons(9); // 9 代表FeedBack信息
            bp2_to_send->reserved = htonl(0);
            bp2_to_send->payload_size = htonl(0);

            // 计算延迟
            struct timeval tv;
            gettimeofday(&tv, NULL);
            uint64_t current_time = (uint64_t)tv.tv_sec * 1000000 + (uint64_t)tv.tv_usec;

            if (current_time < request.original_timestamp) {
                continue;
            }

            uint64_t latency_us = current_time - request.original_timestamp;
            bp2_to_send->timestamp = htobe64(latency_us); // 将延迟作为时间戳发回
            
            // ESP_LOGI(TAG, "Sender Task: Sending feedback with latency=%" PRIu64 "us" "original_ts=%" PRIu64, latency_us, request.original_timestamp);
            
            // 发送数据包
            if (!websocket_->Send(reinterpret_cast<const char*>(serialized_data.data()), serialized_data.size(), true)) {
                 ESP_LOGE(TAG, "Sender Task: Failed to send feedback packet.");
            }
        }
    }
}

void WebsocketProtocol::SendPlaybackTimestamp(uint64_t timestamp)
{
    if (websocket_ == nullptr || !websocket_->IsConnected()) {
        return;
    }

    if (version_ == 2) {
        std::string serialized_data;
        serialized_data.resize(sizeof(BinaryProtocol2) + 0);
        auto bp2_to_send = reinterpret_cast<BinaryProtocol2*>(serialized_data.data());
        bp2_to_send->version = htons(version_);
        bp2_to_send->type = htons(10); // 10 代表末尾时间戳
        bp2_to_send->reserved = htonl(0);
        bp2_to_send->timestamp = htobe64(timestamp);
        bp2_to_send->payload_size = htonl(0);

        if (!websocket_->Send(reinterpret_cast<const char*>(serialized_data.data()), serialized_data.size(), true)) {
            ESP_LOGE(TAG, "Failed to Send End Timestamp.");
        }
        else {
            ESP_LOGI(TAG, "Send End Timestamp %lld.", timestamp);
        }
    }
}