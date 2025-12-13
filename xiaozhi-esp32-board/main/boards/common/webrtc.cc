#include "board.h"
#include "webrtc.h"
#include "media_lib_os.h"
#include "mbedtls/ssl.h"
#include <esp_log.h>
#include <esp_random.h>

#define WEBRTC_DATA_CH_SEND_CACHE_SIZE (4 * 1024)
#define WEBRTC_DATA_CH_RECV_CACHE_SIZE (4 * 1024)
#define DATA_CHANNEL_ENABLED (1)
#define VIDEO_CALL_RING_CMD          "RING"
#define VIDEO_CALL_CALL_ACCEPTED_CMD "ACCEPT_CALL"
#define SAME_STR(a, b) (strncmp(a, b, sizeof(b) - 1) == 0)
#define SEND_CMD(webrtc, cmd) \
    esp_webrtc_send_custom_data(webrtc, ESP_WEBRTC_CUSTOM_DATA_VIA_SIGNALING, (uint8_t *)cmd, strlen(cmd))

static const char *TAG = "webrtc_helper";



static int video_call_on_cmd(esp_webrtc_custom_data_via_t via, uint8_t *data, int size, void *ctx)
{
    ESP_LOGI(TAG, "video_call_on_cmd");
    ctxForWebrtc ctx_group = (*(ctxForWebrtc*)ctx);
    esp_webrtc_handle_t webrtc = ctx_group.webrtc;
    EventGroupHandle_t event_group = ctx_group.event_group;
    if (size == 0 || webrtc == NULL) {
        return 0;
    }
    ESP_LOGI(TAG, "Receive command %.*s", size, (char *)data);

    const char *cmd = (const char *)data;
    ESP_LOGI(TAG, "Processing command: %s", cmd);
    if (SAME_STR(cmd, VIDEO_CALL_RING_CMD)) {
        SEND_CMD(webrtc, VIDEO_CALL_CALL_ACCEPTED_CMD);
        esp_webrtc_enable_peer_connection(webrtc, true);
    }
    // Answer for peer call
    else if (SAME_STR(cmd, VIDEO_CALL_CALL_ACCEPTED_CMD)) {
        esp_webrtc_enable_peer_connection(webrtc, true);
    } 
    else if (SAME_STR(cmd, "CLOSE"))
    {
        xEventGroupSetBits(event_group, (1<<8)); //close event     
    }
    else if (SAME_STR(cmd, "change_fps"))
    {
        esp_webrtc_set_fps(webrtc, 1);
    }

    return 0;
}

/*
 * Mbed TLS 调试日志的回调函数
 * ctx:   用户上下文 (这里我们不用，为 NULL)
 * level: 日志级别
 * file:  源文件名
 * line:  代码行号
 * str:   日志内容
 */


static int webrtc_event_handler(esp_webrtc_event_t *event, void *ctx)
{
    if (event->type == ESP_WEBRTC_EVENT_CONNECTED) {
        ESP_LOGI(TAG,"webrtc connected");
    } else if (event->type == ESP_WEBRTC_EVENT_CONNECT_FAILED || event->type == ESP_WEBRTC_EVENT_DISCONNECTED) {
        ESP_LOGI(TAG,"webrtc disconnect!!");
    }
    return 0;
}

static void custom_media_lib_scheduler(const char *thread_name, media_lib_thread_cfg_t *thread_cfg)
{
    if (strcmp(thread_name, "pc_task") == 0) {
        thread_cfg->stack_size = 12 * 1024;
        thread_cfg->priority = 10;              //default
        thread_cfg->core_id = 0;                //default
    }
}

static void capture_test_scheduler(const char *thread_name, esp_capture_thread_schedule_cfg_t *schedule_cfg)
{
    if (strcmp(thread_name, "buffer_in") == 0) {
        // AEC feed task can have high priority
        schedule_cfg->stack_size = 6 * 1024;
        schedule_cfg->priority = 10;
        schedule_cfg->core_id = 0;
    } else if (strcmp(thread_name, "venc_0") == 0) {
        // For H264 may need huge stack if use hardware encoder can set it to small value
        schedule_cfg->core_id = 0;
        schedule_cfg->stack_size = 60 * 1024;
        schedule_cfg->priority = 1;
    } else if (strcmp(thread_name, "venc_1") == 0) {
        // For H264 may need huge stack if use hardware encoder can set it to small value
        schedule_cfg->core_id = 1;
        schedule_cfg->stack_size = 40 * 1024;
        schedule_cfg->priority = 1;
    } else if (strcmp(thread_name, "aenc_0") == 0) {
        // For OPUS encoder it need huge stack, when use G711 can set it to small value
        schedule_cfg->stack_size = 60 * 1024;
        schedule_cfg->priority = 2;
        schedule_cfg->core_id = 1;
    } else if (strcmp(thread_name, "AUD_SRC") == 0) {
        schedule_cfg->priority = 15;
    }
}


int webrtcHelper::start_webrtc(EventGroupHandle_t event_group)
{
    // generate random room id
    uint32_t rand_num = esp_random();  
    uint32_t nine_digit = 100000000 + (rand_num % 900000000);
    
    room_id = nine_digit;
    char signal_url_buffer[64];  // 预留足够大缓冲区
    sprintf(signal_url_buffer, "https://webrtc.espressif.com/join/%lu", room_id);
    ESP_LOGI(TAG, "room id is %lu", room_id);

    if (webrtc) {
        esp_webrtc_close(webrtc);
        webrtc = NULL;
    }

    esp_peer_default_cfg_t peer_default_cfg = {
        .agent_recv_timeout = 100,   // Enlarge this value if network is poor
        .data_ch_cfg = {
            .send_cache_size = 1536, // Should big than one MTU size
            .recv_cache_size = 1536, // Should big than one MTU size
        },
        .rtp_cfg = {
            .audio_recv_jitter = {
                .cache_size = 1024,
            },
            .send_pool_size = 4096,
            .send_queue_num = 10,
        },
    };

    esp_webrtc_cfg_t cfg = {
        .signaling_impl = esp_signaling_get_apprtc_impl(),
        .signaling_cfg = {
            .signal_url = signal_url_buffer,
            .ctx = &webrtc,
        },
        .peer_impl = esp_peer_get_default_impl(),
        .peer_cfg = {
            .audio_info = {
                .codec = ESP_PEER_AUDIO_CODEC_OPUS,
                .sample_rate = 16000,
            },
            .video_info = {
                .codec = ESP_PEER_VIDEO_CODEC_H264,
                .width = 320,
                .height = 240,
                .fps = 3,
            },
            .audio_dir = ESP_PEER_MEDIA_DIR_NONE,
            .video_dir = ESP_PEER_MEDIA_DIR_SEND_ONLY,
            .enable_data_channel = true,
            .video_over_data_channel = false,
            .no_auto_reconnect = false,
            
            .extra_cfg = &peer_default_cfg,
            .extra_size = sizeof(peer_default_cfg),
            .ctx = &ctx_group,
            .on_custom_data = video_call_on_cmd,
        },
    };
    esp_webrtc_media_provider_t media_provider = {
        .capture = capture_handle_,
        .player = NULL,
    };

    int ret = esp_webrtc_open(&cfg, &webrtc);
    if (ret != 0) {
        ESP_LOGE(TAG, "Fail to open webrtc");
        return ret;
    }
    ctx_group.webrtc = webrtc;
    ctx_group.event_group = event_group;

    media_lib_thread_set_schedule_cb(custom_media_lib_scheduler);
    esp_webrtc_set_media_provider(webrtc, &media_provider);
    // Set event handler
    esp_webrtc_set_event_handler(webrtc, webrtc_event_handler, webrtc);
    esp_capture_set_thread_scheduler(capture_test_scheduler);

    // Default disable auto connect of peer connection
    esp_webrtc_enable_peer_connection(webrtc, false);

    ret = esp_webrtc_start(webrtc);
    if (ret != 0) {
        ESP_LOGE(TAG, "Fail to start webrtc");
    }
    ESP_LOGI(TAG,"Open webrtc success!");

    return ret;
}
int webrtcHelper::stop_webrtc(void)
{
    if (webrtc) {
        esp_webrtc_handle_t handle = webrtc;
        webrtc = NULL;
        ESP_LOGI(TAG, "Start to close webrtc %p", handle);
        esp_webrtc_close(handle);
    }
    return 0;
}

int webrtcHelper::set_bitrate(uint32_t bitrate)
{
    if (webrtc) {
        esp_webrtc_set_bitrate(webrtc, bitrate);
    }
    return 0;
}

int webrtcHelper::set_fps(uint32_t fps)
{
    if (webrtc) {
        esp_webrtc_set_fps(webrtc, fps);
    }
    return 0;
}

int webrtcHelper::set_qp(uint32_t min_qp,uint32_t max_qp)
{
    if (webrtc) {
        esp_webrtc_set_qp(webrtc, min_qp, max_qp);
    }
    return 0;
}

int webrtcHelper::set_gop(uint32_t gop)
{
    if (webrtc) {
        esp_webrtc_set_gop(webrtc, gop);
    }
    return 0;
}

int webrtcHelper::start_stream(void)
{
    if (!webrtc)
    {
        return -1;
    }
    if (stream_started)
    {
        ESP_LOGW(TAG, "Stream already started");
        return -1;
    }
    int ret = esp_webrtc_start_stream(webrtc);
    if (ret == ESP_CAPTURE_ERR_OK) {
        stream_started = true;
        ESP_LOGI(TAG, "Start stream success");
    }
    return ret;
}

int webrtcHelper::stop_stream(void)
{
    if (!webrtc)
    {
        return -1;
    }
    if (!stream_started)
    {
        ESP_LOGW(TAG, "Stream already stopped");
        return -1;
    }
    int ret = esp_webrtc_stop_stream(webrtc);
    if (ret == ESP_CAPTURE_ERR_OK) {
        stream_started = false;
        ESP_LOGI(TAG, "Stop stream success");
    }
    return ret;
}