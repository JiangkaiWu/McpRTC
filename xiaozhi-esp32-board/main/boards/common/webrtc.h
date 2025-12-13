#include <esp_peer.h>
#include <esp_peer_default.h>
#include <esp_peer_signaling.h>
#include <esp_webrtc.h>
#include <esp_webrtc_defaults.h>
#include <esp_capture.h>
#include <esp_capture_sink.h>
#include <esp_capture_video_dvp_src.h>
#include <esp_capture_audio_dev_src.h>
#include "esp_audio_enc_default.h"
#include "esp_video_enc_default.h"
#include "esp_video_dec_default.h"
#include "esp_audio_dec_default.h"
#include <media_lib_os_reg.h>
#include <freertos/event_groups.h>

#ifndef WEBRTC_H
#define WEBRTC_H

struct ctxForWebrtc {
    esp_webrtc_handle_t webrtc;
    EventGroupHandle_t event_group;
};

class webrtcHelper{
    public:
        uint32_t room_id;
        esp_webrtc_handle_t webrtc ;
        esp_capture_video_src_if_t* video_source_;
        esp_capture_audio_src_if_t* audio_source_;
        esp_capture_sink_handle_t capture_handle_;
        ctxForWebrtc ctx_group;
        bool stream_started = true;
        
        webrtcHelper(){
            webrtc = NULL;
            video_source_ = nullptr;
            audio_source_ = nullptr;
            capture_handle_ = NULL;
        }
        int start_webrtc(EventGroupHandle_t event_group);
        int stop_webrtc(void);
        int set_fps(uint32_t fps);
        int set_qp(uint32_t min_qp,uint32_t max_qp);
        int set_gop(uint32_t gop);
        int set_bitrate(uint32_t bitrate);
        int start_stream(void);
        int stop_stream(void);
};

#endif // WEBRTC_H