import requests
import json
import base64
import os
from io import BytesIO
from typing import List, Dict, Any, Optional
from PIL import Image
from core.config import ConfigManager
from utils.prompts import get_gemini_ocr_translation_prompt


class OpenAIProvider:
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.last_error = None
        self.api_key = None
        self.base_url = None
        self.model_name = None
        self._initialize_client()

    def reload_client(self):
        self._initialize_client()

    def _initialize_client(self):
        self.api_key = self.config_manager.get("OpenAIAPI", "api_key")
        self.base_url = self.config_manager.get(
            "OpenAIAPI", "base_url", "https://api.openai.com/v1"
        ).rstrip("/")
        self.model_name = self.config_manager.get("OpenAIAPI", "model_name", "gpt-4o")

    def get_last_error(self) -> Optional[str]:
        return self.last_error

    def _encode_image_to_base64(self, pil_image: Image.Image) -> str:
        buffered = BytesIO()
        pil_image.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode("utf-8")

    def process_image(
        self, pil_image: Image.Image, progress_callback=None, cancellation_event=None
    ) -> Optional[List[Dict[str, Any]]]:
        self.last_error = None
        if not self.api_key:
            self.last_error = "OpenAI API Key 未配置。"
            return None
        target_language = self.config_manager.get(
            "OpenAIAPI", "target_language", "Chinese"
        )
        source_language = (
            self.config_manager.get(
                "OpenAIAPI", "source_language", fallback="Japanese"
            ).strip()
            or "Japanese"
        )
        raw_glossary_text = self.config_manager.get(
            "GeminiAPI", "glossary_text", fallback=""
        ).strip()
        glossary_section = ""
        if raw_glossary_text:
            glossary_lines = [
                line.strip()
                for line in raw_glossary_text.splitlines()
                if line.strip() and "->" in line.strip()
            ]
            if glossary_lines:
                actual_glossary_content = "\n".join(glossary_lines)
                glossary_section = f"""
IMPORTANT: When translating, strictly adhere to the following glossary (source_term->target_term format). Apply these translations wherever applicable:
<glossary>
{actual_glossary_content}
</glossary>
"""
        prompt_text = get_gemini_ocr_translation_prompt(
            source_language, target_language, glossary_section
        )
        if cancellation_event and cancellation_event.is_set():
            return None
        base64_image = self._encode_image_to_base64(pil_image)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}"
                            },
                        },
                    ],
                }
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 4096,
        }
        try:
            if progress_callback:
                progress_callback(
                    25, f"发送请求给 OpenAI Compatible API ({self.model_name})..."
                )
            timeout = int(self.config_manager.get("OpenAIAPI", "request_timeout", "60"))
            proxies = {}
            if self.config_manager.getboolean("Proxy", "enabled", fallback=False):
                host = self.config_manager.get("Proxy", "host")
                port = self.config_manager.get("Proxy", "port")
                if host and port:
                    proxy_url = f"http://{host}:{port}"
                    proxies = {"http": proxy_url, "https": proxy_url}
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=timeout,
                proxies=proxies,
            )
            if cancellation_event and cancellation_event.is_set():
                return None
            response.raise_for_status()
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            if not content:
                self.last_error = "OpenAI API 返回内容为空。"
                return None
            return self._parse_json_response(content)
        except Exception as e:
            self.last_error = f"OpenAI API 请求失败: {e}"
            if hasattr(e, "response") and e.response is not None:
                self.last_error += f" Response: {e.response.text}"
            return None

    def _parse_json_response(self, raw_text: str) -> Optional[List[Dict[str, Any]]]:
        cleaned_json_text = raw_text.strip()
        if cleaned_json_text.startswith("```json"):
            cleaned_json_text = cleaned_json_text[7:]
            if cleaned_json_text.endswith("```"):
                cleaned_json_text = cleaned_json_text[:-3]
        elif cleaned_json_text.startswith("```"):
            cleaned_json_text = cleaned_json_text[3:]
            if cleaned_json_text.endswith("```"):
                cleaned_json_text = cleaned_json_text[:-3]
        cleaned_json_text = cleaned_json_text.strip()
        try:
            data = json.loads(cleaned_json_text)
            items = []
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                if "blocks" in data:
                    items = data["blocks"]
                elif "text_blocks" in data:
                    items = data["text_blocks"]
                else:
                    for v in data.values():
                        if isinstance(v, list):
                            items = v
                            break
            processed_data = []
            for item_idx, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                if (
                    "bounding_box" in item
                    and isinstance(item["bounding_box"], list)
                    and len(item["bounding_box"]) == 4
                ):
                    try:
                        y_min, x_min, y_max, x_max = [
                            int(c) for c in item["bounding_box"]
                        ]
                        x_min_n = max(0.0, min(1.0, x_min / 1000.0))
                        y_min_n = max(0.0, min(1.0, y_min / 1000.0))
                        x_max_n = max(0.0, min(1.0, x_max / 1000.0))
                        y_max_n = max(0.0, min(1.0, y_max / 1000.0))
                        final_x_min = min(x_min_n, x_max_n)
                        final_y_min = min(y_min_n, y_max_n)
                        final_x_max = max(x_min_n, x_max_n)
                        final_y_max = max(y_min_n, y_max_n)
                        item["bbox_norm"] = [
                            final_x_min,
                            final_y_min,
                            final_x_max,
                            final_y_max,
                        ]
                        item["id"] = f"openai_multimodal_{item_idx}"
                        processed_data.append(item)
                    except (ValueError, TypeError):
                        continue
                else:
                    continue
            return processed_data
        except json.JSONDecodeError as e:
            self.last_error = f"解析 JSON 失败: {e}"
            return None
