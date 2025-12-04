import os
import time
import threading
from PyQt6.QtCore import QThread, pyqtSignal, QTimer, QObject
from core.config import ConfigManager
from core.processor import ImageProcessor
from utils.image import draw_processed_blocks_pil

if draw_processed_blocks_pil:
    from PIL import Image


class SmoothProgressEmitter(QObject):
    """单独的对象用于在主线程中管理平滑进度条更新"""

    progress_tick = pyqtSignal(int)

    def __init__(self, timeout_seconds: float, parent=None):
        super().__init__(parent)
        self.timeout_seconds = max(timeout_seconds, 1.0)
        self.current_progress = 0.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_tick)
        self.update_interval_ms = 100
        self.increment_per_tick = 100.0 / (
            self.timeout_seconds * 1000.0 / self.update_interval_ms
        )

    def start(self):
        self.current_progress = 0.0
        self.timer.start(self.update_interval_ms)

    def stop(self):
        self.timer.stop()

    def _on_tick(self):
        self.current_progress += self.increment_per_tick
        if self.current_progress >= 100.0:
            self.current_progress = 100.0
            self.timer.stop()
        self.progress_tick.emit(int(self.current_progress))


class TranslationWorker(QThread):
    progress_signal = pyqtSignal(int, str)
    progress_bar_only_signal = pyqtSignal(int)
    status_text_only_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(object, object, str, str)

    def __init__(self, image_processor: ImageProcessor, image_path: str, parent=None):
        super().__init__(parent)
        self.image_processor = image_processor
        self.image_path = image_path
        self.cancellation_event = threading.Event()
        config_manager = self.image_processor.config_manager
        ocr_provider = config_manager.get(
            "API", "ocr_provider", fallback="gemini"
        ).lower()
        if ocr_provider == "openai":
            self.timeout_seconds = config_manager.getint(
                "OpenAIAPI", "request_timeout", fallback=60
            )
        else:
            self.timeout_seconds = config_manager.getint(
                "GeminiAPI", "request_timeout", fallback=60
            )

    def run(self):
        try:

            def _progress_update(percentage, message):
                if self.cancellation_event.is_set():
                    raise InterruptedError("处理已取消")
                self.status_text_only_signal.emit(message)

            result_tuple = self.image_processor.process_image(
                self.image_path,
                progress_callback=_progress_update,
                cancellation_event=self.cancellation_event,
            )
            if self.cancellation_event.is_set():
                self.finished_signal.emit(None, None, self.image_path, "处理已取消。")
            elif result_tuple:
                original_img, blocks = result_tuple
                for block in blocks:
                    if not hasattr(block, "main_color"):
                        block.main_color = None
                    if not hasattr(block, "outline_color"):
                        block.outline_color = None
                    if not hasattr(block, "background_color"):
                        block.background_color = None
                    if not hasattr(block, "outline_thickness"):
                        block.outline_thickness = None
                    if not hasattr(block, "shape_type"):
                        block.shape_type = "box"
                self.finished_signal.emit(
                    original_img,
                    blocks,
                    self.image_path,
                    self.image_processor.get_last_error(),
                )
            else:
                self.finished_signal.emit(
                    None,
                    None,
                    self.image_path,
                    self.image_processor.get_last_error() or "图片处理失败",
                )
        except InterruptedError:
            self.finished_signal.emit(None, None, self.image_path, "处理已取消。")
        except Exception as e:
            import traceback

            print(f"Error in TranslationWorker: {e}\n{traceback.format_exc()}")
            self.finished_signal.emit(
                None, None, self.image_path, f"工作线程意外错误: {e}"
            )

    def cancel(self):
        self.cancellation_event.set()


class BatchTranslationWorker(QThread):
    overall_progress_signal = pyqtSignal(int, str)
    file_completed_signal = pyqtSignal(str, str, bool)
    batch_finished_signal = pyqtSignal(int, int, float, bool)

    def __init__(
        self,
        image_processor: ImageProcessor,
        config_manager: ConfigManager,
        file_paths: list[str],
        output_dir: str,
        parent=None,
    ):
        super().__init__(parent)
        self.image_processor = image_processor
        self.config_manager = config_manager
        self.file_paths = file_paths
        self.output_dir = output_dir
        self.cancellation_event = threading.Event()

    def run(self):
        processed_count = 0
        error_count = 0
        start_batch_time = time.time()
        total_files = len(self.file_paths)
        cancelled_early = False
        if total_files == 0:
            self.batch_finished_signal.emit(0, 0, 0, False)
            return
        for i, file_path in enumerate(self.file_paths):
            if self.cancellation_event.is_set():
                cancelled_early = True
                break
            current_file_basename = os.path.basename(file_path)
            self.overall_progress_signal.emit(
                int((i / total_files) * 100),
                f"处理中: {current_file_basename} ({i+1}/{total_files})",
            )
            try:
                result_tuple = self.image_processor.process_image(
                    file_path,
                    progress_callback=None,
                    cancellation_event=self.cancellation_event,
                )
            except InterruptedError:
                cancelled_early = True
                break
            except Exception as proc_e:
                self.file_completed_signal.emit(
                    file_path, f"处理时发生意外错误 {proc_e}", False
                )
                error_count += 1
                continue
            if self.cancellation_event.is_set():
                cancelled_early = True
                break
            if result_tuple:
                original_pil, blocks = result_tuple
                last_proc_error = self.image_processor.get_last_error()
                for block in blocks:
                    if not hasattr(block, "main_color"):
                        block.main_color = None
                    if not hasattr(block, "outline_color"):
                        block.outline_color = None
                    if not hasattr(block, "background_color"):
                        block.background_color = None
                    if not hasattr(block, "outline_thickness"):
                        block.outline_thickness = None
                    if not hasattr(block, "shape_type"):
                        block.shape_type = "box"
                final_drawn_pil_image = draw_processed_blocks_pil(
                    original_pil, blocks, self.config_manager
                )
                if final_drawn_pil_image:
                    base, ext = os.path.splitext(current_file_basename)
                    output_filename = f"{base}_translated{ext if ext.lower() in ['.png', '.jpg', '.jpeg', '.bmp'] else '.png'}"
                    output_path = os.path.join(self.output_dir, output_filename)
                    try:
                        save_format = "PNG"
                        if output_filename.lower().endswith((".jpg", ".jpeg")):
                            save_format = "JPEG"
                        elif output_filename.lower().endswith(".bmp"):
                            save_format = "BMP"
                        if (
                            save_format == "JPEG"
                            and final_drawn_pil_image.mode == "RGBA"
                        ):
                            bg = Image.new(
                                "RGB", final_drawn_pil_image.size, (255, 255, 255)
                            )
                            bg.paste(
                                final_drawn_pil_image,
                                mask=final_drawn_pil_image.split()[3],
                            )
                            bg.save(output_path, save_format, quality=95)
                        else:
                            final_drawn_pil_image.save(output_path, save_format)
                        self.file_completed_signal.emit(file_path, output_path, True)
                        processed_count += 1
                    except Exception as e:
                        self.file_completed_signal.emit(
                            file_path, f"保存失败 {output_path}: {e}", False
                        )
                        error_count += 1
                else:
                    err_msg = f"绘制文本块失败: {current_file_basename}" + (
                        f" (原始处理错误: {last_proc_error})" if last_proc_error else ""
                    )
                    self.file_completed_signal.emit(file_path, err_msg, False)
                    error_count += 1
            else:
                self.file_completed_signal.emit(
                    file_path,
                    self.image_processor.get_last_error()
                    or f"处理失败: {current_file_basename}",
                    False,
                )
                error_count += 1
        duration = time.time() - start_batch_time
        total_attempted = processed_count + error_count
        final_progress = (
            int(((total_attempted) / total_files) * 100) if total_files > 0 else 100
        )
        status_msg = "批量处理已取消。" if cancelled_early else "批量处理完成。"
        self.overall_progress_signal.emit(final_progress, status_msg)
        self.batch_finished_signal.emit(
            processed_count, error_count, duration, cancelled_early
        )

    def cancel(self):
        self.cancellation_event.set()
