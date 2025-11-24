import os
import json
import threading
from typing import List, Dict, Any, Optional
from PIL import Image

try:
    from google import genai
    from google.genai import types as google_genai_types
    GENAI_LIB_AVAILABLE = True
except ImportError:
    GENAI_LIB_AVAILABLE = False
    genai = None
    google_genai_types = None

from core.config import ConfigManager
from utils.prompts import get_gemini_ocr_translation_prompt

class GeminiMultimodalProvider:
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.last_error = None
        self.genai_client: Optional[genai.Client] = None
        self.configured_model_name: Optional[str] = None
        self._initialize_client()

    def reload_client(self):
        self._initialize_client()

    def _initialize_client(self):
        if not GENAI_LIB_AVAILABLE:
            self.last_error = "Google Gen AI 库 (google-genai) 未安装。"
            return

        api_key = self.config_manager.get("GeminiAPI", "api_key")
        try:
            if api_key:
                self.genai_client = genai.Client(api_key=api_key)
            else:
                self.genai_client = genai.Client()
            
            self.configured_model_name = self.config_manager.get(
                "GeminiAPI", "model_name", "gemini-1.5-flash-latest"
            )
            
            # Handle 'models/' prefix if present (though SDK might handle it, it's safer to be aware)
            if self.configured_model_name.startswith("models/"):
                print(f"Info: Model name starts with 'models/'. Using '{self.configured_model_name}'.")

        except Exception as e:
            self.last_error = f"配置 Google Gen AI SDK 客户端时发生错误: {e}"
            self.genai_client = None

    def get_last_error(self) -> Optional[str]:
        return self.last_error

    def process_image(
        self, 
        pil_image: Image.Image, 
        progress_callback=None, 
        cancellation_event: threading.Event = None
    ) -> Optional[List[Dict[str, Any]]]:
        
        self.last_error = None
        
        if not GENAI_LIB_AVAILABLE or not self.genai_client:
            self.last_error = self.last_error or "Gemini 客户端未初始化。"
            return None

        target_language = self.config_manager.get("GeminiAPI", "target_language", "Chinese")
        source_language = self.config_manager.get("GeminiAPI", "source_language", fallback="Japanese").strip() or "Japanese"
        
        # Glossary handling
        raw_glossary_text = self.config_manager.get("GeminiAPI", "glossary_text", fallback="").strip()
        glossary_section = ""
        if raw_glossary_text:
            glossary_lines = [line.strip() for line in raw_glossary_text.splitlines() if line.strip() and "->" in line.strip()]
            if glossary_lines:
                actual_glossary_content = "\n".join(glossary_lines)
                glossary_section = f"""
IMPORTANT: When translating, strictly adhere to the following glossary (source_term->target_term format). Apply these translations wherever applicable:
<glossary>
{actual_glossary_content}
</glossary>
"""

        prompt_text = get_gemini_ocr_translation_prompt(source_language, target_language, glossary_section)
        
        if cancellation_event and cancellation_event.is_set():
            return None

        request_contents = [prompt_text, pil_image]
        
        current_generation_config = None
        if google_genai_types:
            # Thinking budget is hardcoded in original, maybe make it configurable later?
            # For now keeping it as is to match original behavior
            thinking_config_obj = google_genai_types.ThinkingConfig(thinking_budget=21145)
            current_generation_config = google_genai_types.GenerateContentConfig(
                temperature=0.5,
                response_mime_type="application/json",
                thinking_config=thinking_config_obj,
            )
        
        try:
            if progress_callback:
                progress_callback(25, f"发送请求给 Gemini ({self.configured_model_name})...")

            response = self.genai_client.models.generate_content(
                model=self.configured_model_name,
                contents=request_contents,
                config=current_generation_config,
            )
            
            if cancellation_event and cancellation_event.is_set():
                return None

            raw_response_text = ""
            if hasattr(response, "text") and response.text:
                raw_response_text = response.text
            elif hasattr(response, "candidates") and response.candidates:
                 # Fallback for candidates access
                 if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                    raw_response_text = "".join(part.text for part in response.candidates[0].content.parts if hasattr(part, "text"))
            
            if not raw_response_text:
                feedback_msg = ""
                if hasattr(response, "prompt_feedback"):
                    feedback_msg = f" Prompt Feedback: {response.prompt_feedback}"
                self.last_error = f"Gemini API 未返回有效内容文本.{feedback_msg}"
                return None

            return self._parse_json_response(raw_response_text)

        except Exception as e:
            self.last_error = f"Gemini API 调用/处理时发生错误: {e}"
            import traceback
            traceback.print_exc()
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
        
        if not cleaned_json_text or cleaned_json_text == "[]":
            return []

        try:
            data = json.loads(cleaned_json_text)
            if isinstance(data, list):
                processed_data = []
                for item_idx, item in enumerate(data):
                    if not isinstance(item, dict):
                        continue
                    
                    # Normalize BBox
                    if "bounding_box" in item and isinstance(item["bounding_box"], list) and len(item["bounding_box"]) == 4:
                        try:
                            y_min, x_min, y_max, x_max = [int(c) for c in item["bounding_box"]]
                            
                            x_min_n = max(0.0, min(1.0, x_min / 1000.0))
                            y_min_n = max(0.0, min(1.0, y_min / 1000.0))
                            x_max_n = max(0.0, min(1.0, x_max / 1000.0))
                            y_max_n = max(0.0, min(1.0, y_max / 1000.0))
                            
                            final_x_min = min(x_min_n, x_max_n)
                            final_y_min = min(y_min_n, y_max_n)
                            final_x_max = max(x_min_n, x_max_n)
                            final_y_max = max(y_min_n, y_max_n)
                            
                            item["bbox_norm"] = [final_x_min, final_y_min, final_x_max, final_y_max]
                            item["id"] = f"gemini_multimodal_{item_idx}"
                            processed_data.append(item)
                        except (ValueError, TypeError):
                            print(f"Warning: Failed to normalize bbox for item {item_idx}")
                            continue
                    else:
                         # Skip items without valid bbox
                         continue
                return processed_data
            else:
                self.last_error = f"Gemini 返回非JSON列表: {cleaned_json_text[:100]}..."
                return None
        except json.JSONDecodeError as e:
            self.last_error = f"解析 Gemini JSON失败: {e}"
            return None
