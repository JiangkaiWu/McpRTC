import os, json, uuid
from types import SimpleNamespace
from typing import Any, Dict, List

import requests
from google import genai
from google.genai import types

from core.providers.llm.base import LLMProviderBase
from core.utils.util import check_model_key
from config.logger import setup_logging
from google.generativeai.types import GenerateContentResponse
from requests import RequestException

log = setup_logging()
TAG = __name__


def test_proxy(proxy_url: str, test_url: str) -> bool:
    try:
        resp = requests.get(test_url, proxies={"http": proxy_url, "https": proxy_url})
        return 200 <= resp.status_code < 400
    except RequestException:
        return False


def setup_proxy_env(http_proxy: str | None, https_proxy: str | None):
    """
    分别测试 HTTP 和 HTTPS 代理是否可用，并设置环境变量。
    如果 HTTPS 代理不可用但 HTTP 可用，会将 HTTPS_PROXY 也指向 HTTP。
    """
    test_http_url = "http://www.google.com"
    test_https_url = "https://www.google.com"

    ok_http = ok_https = False

    if http_proxy:
        ok_http = test_proxy(http_proxy, test_http_url)
        if ok_http:
            os.environ["HTTP_PROXY"] = http_proxy
            log.bind(tag=TAG).info(f"配置提供的Gemini HTTPS代理连通成功: {http_proxy}")
        else:
            log.bind(tag=TAG).warning(f"配置提供的Gemini HTTP代理不可用: {http_proxy}")

    if https_proxy:
        ok_https = test_proxy(https_proxy, test_https_url)
        if ok_https:
            os.environ["HTTPS_PROXY"] = https_proxy
            log.bind(tag=TAG).info(f"配置提供的Gemini HTTPS代理连通成功: {https_proxy}")
        else:
            log.bind(tag=TAG).warning(
                f"配置提供的Gemini HTTPS代理不可用: {https_proxy}"
            )

    # 如果https_proxy不可用，但http_proxy可用且能走通https，则复用http_proxy作为https_proxy
    if ok_http and not ok_https:
        if test_proxy(http_proxy, test_https_url):
            os.environ["HTTPS_PROXY"] = http_proxy
            ok_https = True
            log.bind(tag=TAG).info(f"复用HTTP代理作为HTTPS代理: {http_proxy}")

    if not ok_http and not ok_https:
        log.bind(tag=TAG).error(
            f"Gemini 代理设置失败: HTTP 和 HTTPS 代理都不可用，请检查配置"
        )
        raise RuntimeError("HTTP 和 HTTPS 代理都不可用，请检查配置")


class LLMProvider(LLMProviderBase):
    def __init__(self, cfg: Dict[str, Any]):
        self.model_name = cfg.get("model_name", "gemini-2.5-flash")
        self.api_key = cfg["api_key"]
        # 设置请求超时（秒）
        self.timeout = cfg.get("timeout", 120)  # 默认120秒
        http_proxy = cfg.get("http_proxy")
        https_proxy = cfg.get("https_proxy")

        model_key_msg = check_model_key("LLM", self.api_key)
        if model_key_msg:
            log.bind(tag=TAG).error(model_key_msg)

        use_proxy = False
        # if http_proxy or https_proxy:
        #     log.bind(tag=TAG).info(
        #         f"检测到Gemini代理配置，开始测试代理连通性和设置代理环境..."
        #     )
        #     setup_proxy_env(http_proxy, https_proxy)
        #     log.bind(tag=TAG).info(
        #         f"Gemini 代理设置成功 - HTTP: {http_proxy}, HTTPS: {https_proxy}"
        #     )
        #     use_proxy = True
        os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7890"
        os.environ["HTTP_PROXY"] = "http://127.0.0.1:7890"
        self.client = genai.Client(api_key=self.api_key)



        # 创建模型实例
        # self.model = genai.GenerativeModel(self.model_name)

        self.gen_cfg = types.GenerateContentConfig(
            temperature=0.7,
            top_p=0.9,
            top_k=40,
            max_output_tokens=2048,
        )

    @staticmethod
    def _build_tools(funcs: List[Dict[str, Any]] | None):
        if not funcs:
            return None
        return [
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name=f["function"]["name"],
                        description=f["function"]["description"],
                        parameters=f["function"]["parameters"],
                    )
                    for f in funcs
                ]
            )
        ]
    

    # Gemini文档提到，无需维护session-id，直接用dialogue拼接而成
    def response(self, session_id, dialogue, **kwargs):
        yield from self._generate(dialogue, None)

    def response_with_functions(self, session_id, dialogue, functions=None):
        yield from self._generate(dialogue, self._build_tools(functions))

    def _generate(self, dialogue, tools):
        self.gen_cfg = types.GenerateContentConfig(
            tools=tools
        )
        role_map = {"assistant": "model", "user": "user"}
        contents: list = []
        tested = False
        
        # 拼接对话
        for m in dialogue:
            r = m["role"]
            # print(f"进入for循环,当前m.role是{r}")

            if r == "assistant" and "tool_calls" in m:
                tc = m["tool_calls"][0]
                contents.append(
                    types.Content(
                        role="model",
                        parts=[
                            types.Part.from_function_call(
                                name=tc["function"]["name"],
                                args=json.loads(tc["function"]["arguments"]),
                            )
                        ],
                    )
                )
                continue

            if r == "tool":
                try:
                    print(m.get("tool_call_name",""))
                    print(m.get("content",""))
                    contents.append(
                        types.Content(
                            parts=[types.Part.from_function_response(
                                name=str(m.get("tool_call_name","")),
                                response={"result": {"text": m.get("content","")}}
                            )],
                            role="user"
                        )
                    )
                    continue
                except Exception as e:
                    print(f"Error occurred: {type(e).__name__}: {e}")
                    import traceback
                    traceback.print_exc()

            parts = []
            content = m.get("content")
            if isinstance(content, str):
                # print(f"纯文本？{content}")
                parts.append(types.Part(text=content))
            elif isinstance(content, list):
                # print(f"多模态？{GenerateContentResponse}")
                for item in content:
                    if isinstance(item, dict):
                        item_type = item.get("type")
                        if item_type == "text":
                            parts.append(types.Part(text=item.get("text", "")))
                        elif item_type == "video_data":
                            print("视频内嵌！")
                            tested = True
                            local_video_url_path = item.get("video_content")
                            # 视频数据（内嵌方式）
                            try:
                                f = open(local_video_url_path, 'rb')
                                video_bytes = f.read()
                                print(f"=== 视频数据检查 ===")
                                print(f"文件路径: {local_video_url_path}")
                                print(f"视频字节数: {len(video_bytes)}")
                                print(f"文件头: {video_bytes[:20]}")
                                f.close()
                            except:
                                pass
                            parts.append(
                                types.Part(
                                    inline_data=types.Blob(
                                        data=video_bytes,
                                        mime_type=item.get("mime_type", "video/mp4")
                                    )
                                )
                            )
                            print("视频数据添加完毕")
                        elif item_type == "image":
                            # 图片数据（内嵌方式）
                            parts.append(
                                types.Part(
                                    inline_data=types.Blob(
                                        data=item.get("data"),
                                        mime_type=item.get("mime_type", "image/jpeg")
                                    )
                                )
                            )
                        elif item_type == "video_url":
                            parts.append(
                                types.Part(file_data=item.get("video_url"))
                            )
            
            if parts:
                contents.append(
                    types.Content(
                        role=role_map.get(r, "user"),
                        parts=parts,
                    )
                )

        # print("对话拼接完毕")
        # print(contents)

        if tested == True:
            print("有视频，无工具调用")
            stream = self.client.models.generate_content_stream(
                model = f"models/{self.model_name}",
                contents = contents,
                config = self.gen_cfg
            )
        else:
            print("无视频，有工具调用")
            stream = self.client.models.generate_content_stream(
                model = f"models/{self.model_name}",
                contents = contents,
                config = self.gen_cfg
            )

        try:
            accumulated_text = ""  # 用于累积文本块
            function_calls = []    # 用于收集函数调用
            
            for chunk in stream:
                if not chunk.candidates:
                    continue
                    
                cand = chunk.candidates[0]
                
                # 检查 finish_reason，判断是否结束
                finish_reason = getattr(cand, 'finish_reason', None)
                
                for part in cand.content.parts:
                    print("执行function call")
                    # a) 函数调用
                    if hasattr(part, "function_call") and part.function_call:
                        fc = part.function_call
                        function_calls.append(
                            SimpleNamespace(
                                id=uuid.uuid4().hex,
                                type="function",
                                function=SimpleNamespace(
                                    name=fc.name,
                                    arguments=json.dumps(
                                        dict(fc.args), ensure_ascii=False
                                    ),
                                ),
                            )
                        )
                    
                    # b) 普通文本
                    elif hasattr(part, "text") and part.text:
                        text_content = part.text
                        print(text_content)
                        print("_" * 80)
                        accumulated_text += text_content
                        
                        # 如果没有启用 tools，直接 yield 文本
                        if tools is None:
                            yield text_content
                        else:
                            # 启用了 tools，返回 (text, None)
                            yield text_content, None
            
            # 流结束后，如果有函数调用，yield 函数调用
            if function_calls:
                # 如果有累积的文本，先返回文本（如果需要的话）
                if accumulated_text and tools is not None:
                    # 文本已经在上面的循环中 yield 过了
                    pass
                
                # 返回函数调用
                yield None, function_calls
            
        finally:
            if tools is not None:
                # function-mode 结束标记
                if not function_calls:  # 只有在没有函数调用时才发送结束标记
                    yield None, None

    # 关闭stream，预留后续打断对话功能的功能方法，官方文档推荐打断对话要关闭上一个流，可以有效减少配额计费和资源占用
    @staticmethod
    def _safe_finish_stream(stream: GenerateContentResponse):
        if hasattr(stream, "resolve"):
            stream.resolve()  # Gemini SDK version ≥ 0.5.0
        elif hasattr(stream, "close"):
            stream.close()  # Gemini SDK version < 0.5.0
        else:
            for _ in stream:  # 兜底耗尽
                pass
