import sys
import os
import time
import threading
import math
import io
from PyQt6.QtWidgets import (
    QMainWindow,
    QApplication,
    QWidget,
    QLabel,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
    QSplitter,
    QFrame,
    QFileDialog,
    QMessageBox,
    QSpacerItem,
    QSizePolicy,
    QDialog,
    QProgressBar,
    QTextEdit,
    QLineEdit,
    QDoubleSpinBox,
    QToolButton,
    QMenu,
    QColorDialog,
    QSpinBox,
)
from PyQt6.QtGui import (
    QAction,
    QIcon,
    QPixmap,
    QPalette,
    QBrush,
    QPainter,
    QColor,
    QImage,
    QPen,
    QTransform,
    QFont,
    QFontMetrics,
    QPainterPath,
    QPolygonF,
    QMouseEvent,
    QWheelEvent,
    QContextMenuEvent,
    QCursor,
)
from PyQt6.QtGui import QResizeEvent
from PyQt6.QtCore import (
    Qt,
    pyqtSlot,
    QSize,
    QThread,
    pyqtSignal,
    QPointF,
    QRectF,
    QLineF,
    QEvent,
    QBuffer,
    QIODevice,
    QTimer,
)
from core.config import ConfigManager
from core.processor import ImageProcessor, ProcessedBlock
from utils.image import (
    PILLOW_AVAILABLE,
    pil_to_qpixmap,
    crop_image_to_circle,
    check_dependencies_availability,
    draw_processed_blocks_pil,
    _render_single_block_pil_for_preview,
)
from utils.font import find_font_path
from ui.dialogs.glossary_settings import GlossarySettingsDialog
from ui.dialogs.settings import SettingsDialog
from ui.dialogs.text_style_settings import TextStyleSettingsDialog
from ui.widgets.text_detail_panel import TextDetailPanel
from ui.main_window.interactive_label import InteractiveLabel
from ui.main_window.editable_text_dialog import EditableTextDialog
from ui.main_window.workers import TranslationWorker, BatchTranslationWorker

if PILLOW_AVAILABLE:
    from PIL import Image, UnidentifiedImageError, ImageDraw, ImageFont as PILImageFont

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Translator")
        self.setGeometry(100, 100, 1200, 800)
        self.config_manager = ConfigManager()
        self.image_processor = ImageProcessor(self.config_manager)
        self.original_pil_for_display: Image.Image | None = None
        self.current_image_path: str | None = None
        self.current_bg_image_path: str | None = None
        self.current_icon_path: str | None = None
        self.translation_worker: TranslationWorker | None = None
        self.batch_worker: BatchTranslationWorker | None = None
        self.text_detail_panel: TextDetailPanel | None = None
        self.splitter = None
        self.original_preview_area = None
        self.interactive_translate_area = None
        self.block_controls_widget = None
        self.block_text_edit_proxy = None
        self.block_font_size_spin = None
        self.block_angle_spin = None
        self.main_color_button = None
        self.outline_color_button = None
        self.background_color_button = None
        self.outline_thickness_spin = None
        self.translate_button = None
        self.download_button = None
        self.progress_widget = None
        self.status_label = None
        self.progress_bar = None
        self.cancel_button = None
        self.setAutoFillBackground(True)
        self._check_dependencies_on_startup()
        self._create_actions()
        self._create_menu_bar()
        self._create_central_widget()
        self._connect_signals()
        self._apply_initial_settings()
        QTimer.singleShot(100, self._initial_splitter_setup)

    def _initial_splitter_setup(self):
        if hasattr(self, "splitter") and self.splitter and self.splitter.count() == 3:
            total_width = self.splitter.width()
            if total_width > 50:
                self.splitter.setSizes(
                    [total_width // 3, total_width // 3, total_width // 3]
                )

    def _check_dependencies_on_startup(self):
        deps = check_dependencies_availability()
        missing = [
            name
            for name, available in deps.items()
            if not available and name == "Pillow"
        ]
        if missing:
            QMessageBox.critical(
                self, "依赖缺失", f"{', '.join(missing)} 库未安装！部分功能将无法使用。"
            )

    def _apply_initial_settings(self):
        bg_path = self.config_manager.get("UI", "background_image_path", fallback="")
        if bg_path and os.path.exists(bg_path):
            bg_pix = QPixmap(bg_path)
            if not bg_pix.isNull():
                self.current_bg_image_path = bg_path
                self._apply_window_background(bg_pix)
            else:
                print(f"Warning: Failed to load background image: {bg_path}")
                self.config_manager.set("UI", "background_image_path", "")
        elif bg_path:
            self.config_manager.set("UI", "background_image_path", "")
        icon_path = self.config_manager.get("UI", "window_icon_path", fallback="")
        if icon_path and os.path.exists(icon_path):
            if self._apply_window_icon(icon_path):
                self.current_icon_path = icon_path
            else:
                print(f"Warning: Failed to apply window icon: {icon_path}")
                self.config_manager.set("UI", "window_icon_path", "")
        elif icon_path:
            self.config_manager.set("UI", "window_icon_path", "")
        if (
            hasattr(self, "interactive_translate_area")
            and self.interactive_translate_area
        ):
            self.interactive_translate_area.reload_style_configs()

    def _create_actions(self):
        self.load_action = QAction("&载入图片", self)
        self.load_batch_action = QAction("批量载入图片(&B)", self)
        self.exit_action = QAction("&退出", self)
        self.api_settings_action = QAction("&API及代理设置", self)
        self.glossary_settings_action = QAction("术语表设置(&T)", self)
        self.text_style_settings_action = QAction("文本样式设置(&Y)", self)
        self.change_bg_action = QAction("更换窗口背景(&G)", self)
        self.set_icon_action = QAction("设置窗口图标(&I)", self)

    def _create_menu_bar(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&文件")
        file_menu.addAction(self.load_action)
        file_menu.addAction(self.load_batch_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)
        option_menu = menu_bar.addMenu("&选项")
        option_menu.addAction(self.change_bg_action)
        option_menu.addAction(self.set_icon_action)
        setting_menu = menu_bar.addMenu("&设置")
        setting_menu.addAction(self.api_settings_action)
        setting_menu.addAction(self.glossary_settings_action)
        setting_menu.addAction(self.text_style_settings_action)

    def _create_central_widget(self):
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.original_preview_area = QLabel("原图")
        self.original_preview_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.original_preview_area.setFrameStyle(
            QFrame.Shape.Panel | QFrame.Shadow.Sunken
        )
        self.original_preview_area.setMinimumSize(300, 400)
        self.original_preview_area.setWordWrap(True)
        self.splitter.addWidget(self.original_preview_area)
        self.interactive_translate_area = InteractiveLabel(self.config_manager, self)
        self.interactive_translate_area.setMinimumSize(300, 400)
        self.splitter.addWidget(self.interactive_translate_area)
        self.text_detail_panel = TextDetailPanel(self)
        self.text_detail_panel.setMinimumSize(300, 400)
        self.splitter.addWidget(self.text_detail_panel)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setStretchFactor(2, 1)
        main_layout.addWidget(self.splitter, 1)
        self.block_controls_widget = QWidget()
        block_controls_layout = QHBoxLayout(self.block_controls_widget)
        block_controls_layout.setContentsMargins(0, 2, 0, 2)
        block_controls_layout.setSpacing(5)
        block_controls_layout.addWidget(QLabel("选中:"))
        self.block_text_edit_proxy = QLineEdit()
        self.block_text_edit_proxy.setReadOnly(True)
        block_controls_layout.addWidget(self.block_text_edit_proxy, 1)
        block_controls_layout.addWidget(QLabel("字号:"))
        self.block_font_size_spin = QDoubleSpinBox()
        self.block_font_size_spin.setRange(5, 200)
        self.block_font_size_spin.setSingleStep(1)
        self.block_font_size_spin.setDecimals(0)
        self.block_font_size_spin.setButtonSymbols(
            QDoubleSpinBox.ButtonSymbols.PlusMinus
        )
        block_controls_layout.addWidget(self.block_font_size_spin)
        block_controls_layout.addWidget(QLabel("角度:"))
        self.block_angle_spin = QDoubleSpinBox()
        self.block_angle_spin.setRange(-360, 360)
        self.block_angle_spin.setSingleStep(1)
        self.block_angle_spin.setDecimals(1)
        self.block_angle_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.PlusMinus)
        self.block_angle_spin.setWrapping(True)
        block_controls_layout.addWidget(self.block_angle_spin)
        block_controls_layout.addSpacing(10)
        block_controls_layout.addWidget(QLabel("主色:"))
        self.main_color_button = self._create_color_button()
        block_controls_layout.addWidget(self.main_color_button)
        block_controls_layout.addWidget(QLabel("描边色:"))
        self.outline_color_button = self._create_color_button()
        block_controls_layout.addWidget(self.outline_color_button)
        block_controls_layout.addWidget(QLabel("描边厚:"))
        self.outline_thickness_spin = QSpinBox()
        self.outline_thickness_spin.setRange(0, 20)
        self.outline_thickness_spin.setSingleStep(1)
        self.outline_thickness_spin.setButtonSymbols(QSpinBox.ButtonSymbols.PlusMinus)
        block_controls_layout.addWidget(self.outline_thickness_spin)
        block_controls_layout.addWidget(QLabel("背景色:"))
        self.background_color_button = self._create_color_button()
        block_controls_layout.addWidget(self.background_color_button)
        block_controls_layout.addStretch(0)
        self.block_controls_widget.setVisible(False)
        main_layout.addWidget(self.block_controls_widget, 0)
        button_widget = QWidget()
        button_layout = QHBoxLayout(button_widget)
        button_layout.setContentsMargins(0, 5, 0, 5)
        self.translate_button = QPushButton("翻译当前图片")
        self.download_button = QPushButton("导出翻译结果")
        self.translate_button.setEnabled(False)
        self.download_button.setEnabled(False)
        button_layout.addSpacerItem(
            QSpacerItem(
                40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
            )
        )
        button_layout.addWidget(self.translate_button)
        button_layout.addSpacing(20)
        button_layout.addWidget(self.download_button)
        button_layout.addSpacerItem(
            QSpacerItem(
                40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
            )
        )
        main_layout.addWidget(button_widget, 0)
        self.progress_widget = QWidget()
        progress_layout = QVBoxLayout(self.progress_widget)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        self.status_label = QLabel("就绪")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        progress_layout.addWidget(self.status_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        progress_layout.addWidget(self.progress_bar)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.clicked.connect(self.cancel_processing)
        self.cancel_button.setVisible(False)
        progress_layout.addWidget(self.cancel_button)
        self.progress_widget.setVisible(False)
        main_layout.addWidget(self.progress_widget, 0)
        self.setCentralWidget(central_widget)

    def _create_color_button(self):
        btn = QToolButton()
        btn.setFixedSize(24, 24)
        btn.setStyleSheet("border: 1px solid gray; background-color: white;")
        return btn

    def _connect_signals(self):
        self.load_action.triggered.connect(self.load_image)
        self.load_batch_action.triggered.connect(self.load_batch_images)
        self.exit_action.triggered.connect(self.close)
        self.api_settings_action.triggered.connect(self.open_api_settings)
        self.glossary_settings_action.triggered.connect(self.open_glossary_settings)
        self.text_style_settings_action.triggered.connect(
            self.open_text_style_settings
        )
        self.change_bg_action.triggered.connect(self.change_window_background)
        self.set_icon_action.triggered.connect(self.set_window_icon)
        self.translate_button.clicked.connect(self.start_translation)
        self.download_button.clicked.connect(self.export_result)
        self.interactive_translate_area.block_modified_signal.connect(
            self.on_block_modified_by_interaction
        )
        self.interactive_translate_area.selection_changed_signal.connect(
            self.on_block_selection_changed
        )
        self.block_font_size_spin.valueChanged.connect(self.on_block_control_changed)
        self.block_angle_spin.valueChanged.connect(self.on_block_control_changed)
        self.outline_thickness_spin.valueChanged.connect(self.on_block_control_changed)
        self.main_color_button.clicked.connect(
            lambda: self.pick_color_for_block("main")
        )
        self.outline_color_button.clicked.connect(
            lambda: self.pick_color_for_block("outline")
        )
        self.background_color_button.clicked.connect(
            lambda: self.pick_color_for_block("background")
        )
        self.text_detail_panel.translated_text_changed_externally_signal.connect(
            self.on_text_panel_modified
        )

    def load_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择图片",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All Files (*)",
        )
        if file_path:
            self.current_image_path = file_path
            self.status_label.setText(f"已加载: {os.path.basename(file_path)}")
            self.translate_button.setEnabled(True)
            self.download_button.setEnabled(False)
            self.interactive_translate_area.clear_all()
            self.text_detail_panel.clear_content()
            self.block_controls_widget.setVisible(False)
            try:
                pil_img = Image.open(file_path)
                self.original_pil_for_display = pil_img.copy()
                q_pix = pil_to_qpixmap(pil_img)
                if q_pix:
                    self.original_preview_area.setPixmap(
                        q_pix.scaled(
                            self.original_preview_area.size(),
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                    )
                    self.interactive_translate_area.set_background_image(q_pix)
                else:
                    self.original_preview_area.setText("无法显示图片")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"无法加载图片: {e}")

    def load_batch_images(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择多张图片",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All Files (*)",
        )
        if not file_paths:
            return
        output_dir = QFileDialog.getExistingDirectory(self, "选择保存翻译结果的文件夹")
        if not output_dir:
            return
        self.start_batch_translation(file_paths, output_dir)

    def start_translation(self):
        if not self.current_image_path:
            return
        self.translate_button.setEnabled(False)
        self.download_button.setEnabled(False)
        self.load_action.setEnabled(False)
        self.load_batch_action.setEnabled(False)
        self.progress_widget.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("正在初始化翻译...")
        self.cancel_button.setVisible(True)
        self.translation_worker = TranslationWorker(
            self.image_processor, self.current_image_path
        )
        self.translation_worker.progress_signal.connect(self.update_progress)
        self.translation_worker.finished_signal.connect(self.translation_finished)
        self.translation_worker.start()

    def start_batch_translation(self, file_paths, output_dir):
        self.translate_button.setEnabled(False)
        self.download_button.setEnabled(False)
        self.load_action.setEnabled(False)
        self.load_batch_action.setEnabled(False)
        self.progress_widget.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("正在准备批量翻译...")
        self.cancel_button.setVisible(True)
        self.batch_worker = BatchTranslationWorker(
            self.image_processor, self.config_manager, file_paths, output_dir
        )
        self.batch_worker.overall_progress_signal.connect(self.update_progress)
        self.batch_worker.file_completed_signal.connect(self.on_batch_file_completed)
        self.batch_worker.batch_finished_signal.connect(self.on_batch_finished)
        self.batch_worker.start()

    def cancel_processing(self):
        if self.translation_worker and self.translation_worker.isRunning():
            self.status_label.setText("正在取消...")
            self.translation_worker.cancel()
            self.cancel_button.setEnabled(False)
        if self.batch_worker and self.batch_worker.isRunning():
            self.status_label.setText("正在取消批量任务...")
            self.batch_worker.cancel()
            self.cancel_button.setEnabled(False)

    @pyqtSlot(int, str)
    def update_progress(self, percentage, message):
        self.progress_bar.setValue(percentage)
        self.status_label.setText(message)

    @pyqtSlot(object, object, str, str)
    def translation_finished(self, original_img, blocks, image_path, error_msg):
        self.translate_button.setEnabled(True)
        self.load_action.setEnabled(True)
        self.load_batch_action.setEnabled(True)
        self.progress_widget.setVisible(False)
        self.cancel_button.setVisible(False)
        self.cancel_button.setEnabled(True)
        if error_msg:
            if "已取消" in error_msg:
                self.status_label.setText("翻译已取消")
                QMessageBox.information(self, "提示", error_msg)
            else:
                self.status_label.setText("翻译出错")
                QMessageBox.warning(self, "翻译失败", f"处理出错: {error_msg}")
            return
        if blocks:
            self.interactive_translate_area.set_processed_blocks(blocks)
            self.download_button.setEnabled(True)
            self.status_label.setText("翻译完成")
            self.text_detail_panel.set_blocks(blocks)
        else:
            self.status_label.setText("未检测到文本或翻译为空")
            QMessageBox.information(self, "提示", "未检测到文本或翻译结果为空。")

    @pyqtSlot(str, str, bool)
    def on_batch_file_completed(self, src_path, result_info, success):
        if not success:
            print(f"Batch Item Failed: {src_path} -> {result_info}")

    @pyqtSlot(int, int, float, bool)
    def on_batch_finished(self, processed, errors, duration, cancelled):
        self.translate_button.setEnabled(True)
        self.load_action.setEnabled(True)
        self.load_batch_action.setEnabled(True)
        self.progress_widget.setVisible(False)
        self.cancel_button.setVisible(False)
        self.cancel_button.setEnabled(True)
        msg = f"批量处理结束。\n成功: {processed}\n失败: {errors}\n耗时: {duration:.2f}秒"
        if cancelled:
            msg += "\n(任务已取消)"
        QMessageBox.information(self, "批量完成", msg)
        self.status_label.setText("批量任务结束")

    def export_result(self):
        if not self.interactive_translate_area.processed_blocks:
            return
        default_name = "translated_image.png"
        if self.current_image_path:
            base = os.path.splitext(os.path.basename(self.current_image_path))[0]
            default_name = f"{base}_translated.png"
        save_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "保存结果",
            default_name,
            "PNG Images (*.png);;JPEG Images (*.jpg *.jpeg);;BMP Images (*.bmp)",
        )
        if save_path:
            final_pil = (
                self.interactive_translate_area.get_current_render_as_pil_image()
            )
            if final_pil:
                try:
                    save_format = "PNG"
                    if save_path.lower().endswith((".jpg", ".jpeg")):
                        save_format = "JPEG"
                    elif save_path.lower().endswith(".bmp"):
                        save_format = "BMP"
                    if save_format == "JPEG" and final_pil.mode == "RGBA":
                        bg = Image.new("RGB", final_pil.size, (255, 255, 255))
                        bg.paste(final_pil, mask=final_pil.split()[3])
                        bg.save(save_path, save_format, quality=95)
                    else:
                        final_pil.save(save_path, save_format)
                    QMessageBox.information(self, "成功", f"图片已保存至: {save_path}")
                except Exception as e:
                    QMessageBox.critical(self, "错误", f"保存失败: {e}")
            else:
                QMessageBox.warning(self, "警告", "无法生成渲染结果，可能缺少背景图或库。")

    def open_api_settings(self):
        dialog = SettingsDialog(self.config_manager, self)
        if dialog.exec():
            self.image_processor.reload_config()

    def open_glossary_settings(self):
        dialog = GlossarySettingsDialog(self.config_manager, self)
        dialog.exec()

    def open_text_style_settings(self):
        dialog = TextStyleSettingsDialog(self.config_manager, self)
        if dialog.exec():
            if self.interactive_translate_area:
                self.interactive_translate_area.reload_style_configs()

    def change_window_background(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择背景图片",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All Files (*)",
        )
        if file_path:
            pixmap = QPixmap(file_path)
            if not pixmap.isNull():
                self.current_bg_image_path = file_path
                self.config_manager.set("UI", "background_image_path", file_path)
                self.config_manager.save()  # 持久化保存
                self._apply_window_background(pixmap)
            else:
                QMessageBox.warning(self, "错误", "无法加载该图片作为背景。")

    def _apply_window_background(self, pixmap: QPixmap):
        # 缩放背景图片
        scaled_pixmap = pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        
        # 降低亮度：在图片上绘制半透明黑色遮罩
        darkened_pixmap = QPixmap(scaled_pixmap.size())
        darkened_pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(darkened_pixmap)
        painter.drawPixmap(0, 0, scaled_pixmap)
        # 绘制半透明黑色遮罩（alpha=128表示50%透明度，可根据需要调整）
        painter.fillRect(darkened_pixmap.rect(), QColor(0, 0, 0, 128))
        painter.end()
        
        # 只为主窗口设置背景
        palette = self.palette()
        palette.setBrush(QPalette.ColorRole.Window, QBrush(darkened_pixmap))
        self.setPalette(palette)
        
        # 为所有三个主面板设置半透明背景和圆角
        panel_style = """
            QLabel, QWidget {
                background-color: rgba(30, 30, 30, 180);
                border-radius: 10px;
            }
        """
        
        # Splitter handle style to avoid "wallpaper coverage" glitch
        splitter_style = """
            QSplitter::handle {
                background-color: transparent;
            }
        """
        self.splitter.setStyleSheet(splitter_style)

        if self.original_preview_area:
            self.original_preview_area.setStyleSheet(panel_style)
        if self.interactive_translate_area:
            self.interactive_translate_area.setStyleSheet(panel_style)
        
        # 右侧文本详情面板：容器透明，文本编辑框有半透明背景和圆角
        if self.text_detail_panel:
            text_panel_style = """
                TextDetailPanel {
                    background-color: transparent;
                }
                QTextEdit {
                    background-color: rgba(30, 30, 30, 180);
                    border-radius: 10px;
                    border: 1px solid rgba(255, 255, 255, 30);
                    color: white;
                    padding: 5px;
                }
            """
            self.text_detail_panel.setStyleSheet(text_panel_style)

    def set_window_icon(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择图标", "", "Images (*.png *.jpg *.jpeg *.ico);;All Files (*)"
        )
        if file_path:
            if self._apply_window_icon(file_path):
                self.current_icon_path = file_path
                self.config_manager.set("UI", "window_icon_path", file_path)
                self.config_manager.save()  # 持久化保存
            else:
                QMessageBox.warning(self, "错误", "无法加载该图片作为图标。")

    def _apply_window_icon(self, icon_path: str) -> bool:
        if os.path.exists(icon_path):
            icon = QIcon(icon_path)
            if not icon.isNull():
                self.setWindowIcon(icon)
                return True
        return False

    def resizeEvent(self, event):
        if self.current_bg_image_path:
            pixmap = QPixmap(self.current_bg_image_path)
            if not pixmap.isNull():
                self._apply_window_background(pixmap)
        super().resizeEvent(event)

    def on_block_modified_by_interaction(self, block: ProcessedBlock):
        if self.text_detail_panel:
            self.text_detail_panel.refresh_block_display(block)
        self.update_block_controls_ui(block)

    def on_block_selection_changed(self, block: ProcessedBlock | None):
        if self.text_detail_panel:
            self.text_detail_panel.select_block(block)
        self.update_block_controls_ui(block)

    def on_text_panel_modified(self, new_text: str, block_id: str):
        """Handle text changes from the text detail panel."""
        if not self.interactive_translate_area.processed_blocks:
            return
        # Find the block with the matching ID
        target_block = None
        for block in self.interactive_translate_area.processed_blocks:
            if hasattr(block, 'id') and str(block.id) == block_id:
                target_block = block
                break
        if target_block:
            target_block.translated_text = new_text
            self.interactive_translate_area._invalidate_block_cache(target_block)
            self.interactive_translate_area.block_modified_signal.emit(target_block)


    def update_block_controls_ui(self, block: ProcessedBlock | None):
        if not block:
            self.block_controls_widget.setVisible(False)
            return
        self.block_controls_widget.setVisible(True)
        self.block_text_edit_proxy.setText(block.translated_text)
        self.block_font_size_spin.blockSignals(True)
        self.block_font_size_spin.setValue(block.font_size_pixels)
        self.block_font_size_spin.blockSignals(False)
        self.block_angle_spin.blockSignals(True)
        self.block_angle_spin.setValue(block.angle)
        self.block_angle_spin.blockSignals(False)
        self.outline_thickness_spin.blockSignals(True)
        th = (
            block.outline_thickness
            if hasattr(block, "outline_thickness")
            and block.outline_thickness is not None
            else self.interactive_translate_area._outline_thickness
        )
        self.outline_thickness_spin.setValue(th)
        self.outline_thickness_spin.blockSignals(False)
        mc = (
            block.main_color
            if hasattr(block, "main_color") and block.main_color is not None
            else self.interactive_translate_area._text_main_color_pil
        )
        self._set_btn_color(self.main_color_button, mc)
        oc = (
            block.outline_color
            if hasattr(block, "outline_color") and block.outline_color is not None
            else self.interactive_translate_area._text_outline_color_pil
        )
        self._set_btn_color(self.outline_color_button, oc)
        bc = (
            block.background_color
            if hasattr(block, "background_color") and block.background_color is not None
            else self.interactive_translate_area._text_bg_color_pil
        )
        self._set_btn_color(self.background_color_button, bc)

    def _set_btn_color(self, btn: QToolButton, color_tuple):
        if len(color_tuple) == 4:
            c = QColor(
                color_tuple[0], color_tuple[1], color_tuple[2], color_tuple[3]
            )
        else:
            c = QColor(color_tuple[0], color_tuple[1], color_tuple[2])
        pix = QPixmap(16, 16)
        pix.fill(c)
        btn.setIcon(QIcon(pix))

    def on_block_control_changed(self):
        if not self.interactive_translate_area.selected_block:
            return
        block = self.interactive_translate_area.selected_block
        block.font_size_pixels = self.block_font_size_spin.value()
        block.angle = self.block_angle_spin.value()
        block.outline_thickness = self.outline_thickness_spin.value()
        self.interactive_translate_area._invalidate_block_cache(block)
        self.interactive_translate_area.block_modified_signal.emit(block)

    def pick_color_for_block(self, target_type: str):
        block = self.interactive_translate_area.selected_block
        if not block:
            return
        current_color_tuple = (0, 0, 0, 255)
        if target_type == "main":
            current_color_tuple = (
                block.main_color
                if hasattr(block, "main_color") and block.main_color
                else self.interactive_translate_area._text_main_color_pil
            )
        elif target_type == "outline":
            current_color_tuple = (
                block.outline_color
                if hasattr(block, "outline_color") and block.outline_color
                else self.interactive_translate_area._text_outline_color_pil
            )
        elif target_type == "background":
            current_color_tuple = (
                block.background_color
                if hasattr(block, "background_color") and block.background_color
                else self.interactive_translate_area._text_bg_color_pil
            )
        initial = QColor(
            current_color_tuple[0],
            current_color_tuple[1],
            current_color_tuple[2],
            current_color_tuple[3],
        )
        color = QColorDialog.getColor(
            initial, self, "选择颜色", QColorDialog.ColorDialogOption.ShowAlphaChannel
        )
        if color.isValid():
            new_tuple = (color.red(), color.green(), color.blue(), color.alpha())
            if target_type == "main":
                block.main_color = new_tuple
            elif target_type == "outline":
                block.outline_color = new_tuple
            elif target_type == "background":
                block.background_color = new_tuple
            self.update_block_controls_ui(block)
            self.interactive_translate_area._invalidate_block_cache(block)
            self.interactive_translate_area.block_modified_signal.emit(block)
