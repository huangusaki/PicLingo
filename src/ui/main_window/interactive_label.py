import math
import time
import io
from PyQt6.QtWidgets import QWidget, QApplication, QMessageBox, QMenu, QDialog
from PyQt6.QtGui import (
    QPixmap,
    QPainter,
    QColor,
    QPen,
    QTransform,
    QPolygonF,
    QMouseEvent,
    QWheelEvent,
    QContextMenuEvent,
    QImage,
    QResizeEvent,
    QPainterPath,
)
from PyQt6.QtCore import (
    Qt,
    pyqtSignal,
    QPointF,
    QRectF,
    QBuffer,
    QIODevice,
    QEvent,
)
from core.config import ConfigManager
from core.processor import ProcessedBlock
from utils.image import (
    PILLOW_AVAILABLE,
    pil_to_qpixmap,
    draw_processed_blocks_pil,
    _render_single_block_pil_for_preview,
)
from ui.main_window.editable_text_dialog import EditableTextDialog

if PILLOW_AVAILABLE:
    from PIL import Image

CORNER_HANDLE_SIZE = 10
ROTATION_HANDLE_OFFSET = 20

class InteractiveLabel(QWidget):
    block_modified_signal = pyqtSignal(object)
    selection_changed_signal = pyqtSignal(object)

    def _scale_background_and_view(self):
        if self.background_pixmap and not self.background_pixmap.isNull():
            widget_size = self.size()
            img_size = self.background_pixmap.size()
            if (
                img_size.width() <= 0
                or img_size.height() <= 0
                or widget_size.width() <= 0
                or widget_size.height() <= 0
            ):
                self.scaled_background_pixmap = None
                self.current_scale_factor = 1.0
                self.update()
                return
            scale_x = widget_size.width() / img_size.width()
            scale_y = widget_size.height() / img_size.height()
            self.current_scale_factor = min(scale_x, scale_y)
            scaled_width = int(img_size.width() * self.current_scale_factor)
            scaled_height = int(img_size.height() * self.current_scale_factor)
            if scaled_width > 0 and scaled_height > 0:
                self.scaled_background_pixmap = self.background_pixmap.scaled(
                    scaled_width,
                    scaled_height,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            else:
                self.scaled_background_pixmap = None
        else:
            self.scaled_background_pixmap = None
            self.current_scale_factor = 1.0
        self.update()

    def set_background_image(self, pixmap: QPixmap | None):
        """Sets the background image for the interactive area."""
        self.background_pixmap = pixmap
        self.pan_offset = QPointF(0, 0)
        self._scale_background_and_view()
        self.update()

    def clear_all(self):
        """Resets the interactive area completely."""
        self.background_pixmap = None
        self.scaled_background_pixmap = None
        self.processed_blocks = []
        self.set_selected_block(None)
        self._invalidate_block_cache()
        self.current_scale_factor = 1.0
        self.pan_offset = QPointF(0, 0)
        self.dragging_block = False
        self.resizing_block = False
        self.rotating_block = False
        self.initial_block_bbox_on_drag = None
        self.initial_mouse_pos_on_drag = None
        self.resize_anchor_opposite_corner_orig = None
        self.resize_corner = -1
        self.rotation_center_on_rotate = QPointF()
        self.update()

    def __init__(self, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.setMinimumSize(300, 300)
        self.background_pixmap: QPixmap | None = None
        self.scaled_background_pixmap: QPixmap | None = None
        self.processed_blocks: list[ProcessedBlock] = []
        self.selected_block: ProcessedBlock | None = None
        self._block_render_cache: dict[str, tuple[int, QPixmap]] = {}
        self.current_scale_factor = 1.0
        self.pan_offset = QPointF(0, 0)
        self.dragging_block = False
        self.resizing_block = False
        self.rotating_block = False
        self.drag_offset = QPointF()
        self.resize_corner = -1
        self.initial_block_bbox_on_drag: list[float] | None = None
        self.initial_mouse_pos_on_drag: QPointF | None = None
        self.initial_angle_on_rotate = 0.0
        self.rotation_center_on_rotate = QPointF()
        self.resize_anchor_opposite_corner_orig: QPointF | None = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.font_size_mapping = {}
        self.reload_style_configs()
        self.update()

    def _parse_color_str(self, color_str: str, default_color_tuple: tuple) -> tuple:
        try:
            parts = list(map(int, color_str.split(",")))
            if len(parts) == 3:
                return (parts[0], parts[1], parts[2], 255)
            if len(parts) == 4:
                return (parts[0], parts[1], parts[2], parts[3])
        except:
            pass
        return default_color_tuple

    def reload_style_configs(self):
        self._font_name_config = self.config_manager.get("UI", "font_name", "msyh.ttc")
        self._text_main_color_pil = self._parse_color_str(
            self.config_manager.get("UI", "text_main_color", "255,255,255,255"),
            (255, 255, 255, 255),
        )
        self._text_outline_color_pil = self._parse_color_str(
            self.config_manager.get("UI", "text_outline_color", "0,0,0,255"),
            (0, 0, 0, 255),
        )
        self._text_bg_color_pil = self._parse_color_str(
            self.config_manager.get("UI", "text_background_color", "0,0,0,128"),
            (0, 0, 0, 128),
        )
        self._outline_thickness = self.config_manager.getint(
            "UI", "text_outline_thickness", 2
        )
        self._text_padding = self.config_manager.getint("UI", "text_padding", 3)
        self._h_char_spacing_px = self.config_manager.getint(
            "UI", "h_text_char_spacing_px", 0
        )
        self._h_line_spacing_px = self.config_manager.getint(
            "UI", "h_text_line_spacing_px", 0
        )
        self._v_char_spacing_px = self.config_manager.getint(
            "UI", "v_text_char_spacing_px", 0
        )
        self._v_col_spacing_px = self.config_manager.getint(
            "UI", "v_text_column_spacing_px", 0
        )
        self._h_manual_break_extra_px = self.config_manager.getint(
            "UI", "h_manual_break_extra_spacing_px", 0
        )
        self._v_manual_break_extra_px = self.config_manager.getint(
            "UI", "v_manual_break_extra_spacing_px", 0
        )
        self.font_size_mapping = {
            "very_small": self.config_manager.getint(
                "FontSizeMapping", "very_small", 12
            ),
            "small": self.config_manager.getint("FontSizeMapping", "small", 16),
            "medium": self.config_manager.getint("FontSizeMapping", "medium", 22),
            "large": self.config_manager.getint("FontSizeMapping", "large", 28),
            "very_large": self.config_manager.getint(
                "FontSizeMapping", "very_large", 36
            ),
        }
        fixed_font_size_override = self.config_manager.getint(
            "UI", "fixed_font_size", 0
        )
        for block_item in self.processed_blocks:
            if fixed_font_size_override > 0:
                block_item.font_size_pixels = fixed_font_size_override
            else:
                block_item.font_size_pixels = self.font_size_mapping.get(
                    block_item.font_size_category,
                    self.font_size_mapping.get("medium", 22),
                )
            if not hasattr(block_item, "main_color"):
                block_item.main_color = None
            if not hasattr(block_item, "outline_color"):
                block_item.outline_color = None
            if not hasattr(block_item, "background_color"):
                block_item.background_color = None
            if not hasattr(block_item, "outline_thickness"):
                block_item.outline_thickness = None
            self._invalidate_block_cache(block_item)
        self.update()

    def _invalidate_block_cache(self, block: ProcessedBlock | None = None):
        if block and hasattr(block, "id"):
            self._block_render_cache.pop(block.id, None)
        else:
            self._block_render_cache.clear()
        self.update()

    def _get_block_visual_hash(self, block: ProcessedBlock) -> int:
        main_color_to_hash = (
            block.main_color
            if hasattr(block, "main_color") and block.main_color is not None
            else self._text_main_color_pil
        )
        outline_color_to_hash = (
            block.outline_color
            if hasattr(block, "outline_color") and block.outline_color is not None
            else self._text_outline_color_pil
        )
        bg_color_to_hash = (
            block.background_color
            if hasattr(block, "background_color") and block.background_color is not None
            else self._text_bg_color_pil
        )
        outline_thickness_to_hash = (
            block.outline_thickness
            if hasattr(block, "outline_thickness")
            and block.outline_thickness is not None
            else self._outline_thickness
        )
        relevant_attrs = (
            block.translated_text,
            block.font_size_pixels,
            block.orientation,
            block.text_align,
            tuple(block.bbox) if block.bbox else None,
            self._font_name_config,
            main_color_to_hash,
            outline_color_to_hash,
            bg_color_to_hash,
            outline_thickness_to_hash,
            self._text_padding,
            self._h_char_spacing_px,
            self._h_line_spacing_px,
            self._v_char_spacing_px,
            self._v_col_spacing_px,
            self._h_manual_break_extra_px,
            self._v_manual_break_extra_px,
        )
        return hash(relevant_attrs)

    def _get_or_render_block_qpixmap(self, block: ProcessedBlock) -> QPixmap | None:
        if not PILLOW_AVAILABLE or not hasattr(block, "id"):
            return None
        block_id = block.id
        current_version_hash = self._get_block_visual_hash(block)
        if block_id in self._block_render_cache:
            cached_version_hash, cached_pixmap = self._block_render_cache[block_id]
            if (
                cached_version_hash == current_version_hash
                and not cached_pixmap.isNull()
            ):
                return cached_pixmap
        main_color = (
            block.main_color
            if hasattr(block, "main_color") and block.main_color is not None
            else self._text_main_color_pil
        )
        outline_color = (
            block.outline_color
            if hasattr(block, "outline_color") and block.outline_color is not None
            else self._text_outline_color_pil
        )
        bg_color = (
            block.background_color
            if hasattr(block, "background_color") and block.background_color is not None
            else self._text_bg_color_pil
        )
        thickness = (
            block.outline_thickness
            if hasattr(block, "outline_thickness")
            and block.outline_thickness is not None
            else self._outline_thickness
        )
        pil_image = _render_single_block_pil_for_preview(
            block=block,
            font_name_config=self._font_name_config,
            text_main_color_pil=main_color,
            text_outline_color_pil=outline_color,
            text_bg_color_pil=bg_color,
            outline_thickness=thickness,
            text_padding=self._text_padding,
            h_char_spacing_px=self._h_char_spacing_px,
            h_line_spacing_px=self._h_line_spacing_px,
            v_char_spacing_px=self._v_char_spacing_px,
            v_col_spacing_px=self._v_col_spacing_px,
            h_manual_break_extra_px=self._h_manual_break_extra_px,
            v_manual_break_extra_px=self._v_manual_break_extra_px,
        )
        if pil_image:
            q_pixmap = pil_to_qpixmap(pil_image)
            if q_pixmap and not q_pixmap.isNull():
                self._block_render_cache[block_id] = (current_version_hash, q_pixmap)
                return q_pixmap
            else:
                self._block_render_cache.pop(block_id, None)
                return None
        self._block_render_cache.pop(block_id, None)
        return None

    def set_processed_blocks(self, blocks: list[ProcessedBlock]):
        self.processed_blocks = blocks
        self._block_render_cache.clear()
        if self.selected_block not in self.processed_blocks:
            self.set_selected_block(None)
        for i, block in enumerate(self.processed_blocks):
            if not hasattr(block, "id") or block.id is None:
                block.id = f"block_{time.time_ns()}_{i}"
            if not hasattr(block, "main_color"):
                block.main_color = None
            if not hasattr(block, "outline_color"):
                block.outline_color = None
            if not hasattr(block, "background_color"):
                block.background_color = None
            if not hasattr(block, "outline_thickness"):
                block.outline_thickness = None
            fixed_font_size_override = self.config_manager.getint(
                "UI", "fixed_font_size", 0
            )
            if fixed_font_size_override > 0:
                block.font_size_pixels = fixed_font_size_override
            else:
                block.font_size_pixels = self.font_size_mapping.get(
                    getattr(block, "font_size_category", "medium"),
                    self.font_size_mapping.get("medium", 22),
                )
        self.update()

    def get_current_render_as_pil_image(self) -> Image.Image | None:
        if not self.background_pixmap or not PILLOW_AVAILABLE:
            return None
        q_img_bg = self.background_pixmap.toImage().convertToFormat(
            QImage.Format.Format_RGBA8888
        )
        if q_img_bg.isNull():
            return None
        img_buffer = QBuffer()
        img_buffer.open(QIODevice.OpenModeFlag.ReadWrite)
        if not q_img_bg.save(img_buffer, "PNG"):
            return None
        img_buffer.seek(0)
        try:
            pil_bg_image = Image.open(io.BytesIO(img_buffer.data()))
        except Exception:
            return None
        finally:
            img_buffer.close()
        if pil_bg_image.mode != "RGBA":
            pil_bg_image = pil_bg_image.convert("RGBA")
        final_pil_image = draw_processed_blocks_pil(
            pil_bg_image, self.processed_blocks, self.config_manager
        )
        return final_pil_image

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Apply rounded clipping
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 10, 10)
        painter.setClipPath(path)

        bg_draw_x, bg_draw_y = 0, 0
        if self.scaled_background_pixmap and not self.scaled_background_pixmap.isNull():
            bg_draw_x = (self.width() - self.scaled_background_pixmap.width()) / 2.0
            bg_draw_y = (self.height() - self.scaled_background_pixmap.height()) / 2.0
            painter.drawPixmap(
                QPointF(bg_draw_x, bg_draw_y), self.scaled_background_pixmap
            )
        else:
            painter.fillRect(self.rect(), self.palette().window())
            if not self.processed_blocks:
                painter.setPen(Qt.GlobalColor.gray)
                painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "翻译结果")
        bg_img_to_display_scale_x, bg_img_to_display_scale_y = (
            self._get_bg_fit_scale_factors()
        )
        for block in self.processed_blocks:
            block_qpixmap = self._get_or_render_block_qpixmap(block)
            painter.save()
            block_center_x_orig = (block.bbox[0] + block.bbox[2]) / 2.0
            block_center_y_orig = (block.bbox[1] + block.bbox[3]) / 2.0
            block_display_center_x_rel_bg = (
                block_center_x_orig * bg_img_to_display_scale_x
            )
            block_display_center_y_rel_bg = (
                block_center_y_orig * bg_img_to_display_scale_y
            )
            block_display_center_widget_x = bg_draw_x + block_display_center_x_rel_bg
            block_display_center_widget_y = bg_draw_y + block_display_center_y_rel_bg
            content_transform = QTransform()
            content_transform.translate(
                block_display_center_widget_x, block_display_center_widget_y
            )
            content_transform.rotate(block.angle)
            content_transform.scale(
                bg_img_to_display_scale_x, bg_img_to_display_scale_y
            )
            current_painter_transform = painter.worldTransform()
            painter.setWorldTransform(content_transform, combine=True)
            if block_qpixmap and not block_qpixmap.isNull():
                pixmap_draw_x = -block_qpixmap.width() / 2.0
                pixmap_draw_y = -block_qpixmap.height() / 2.0
                painter.drawPixmap(QPointF(pixmap_draw_x, pixmap_draw_y), block_qpixmap)
            painter.setWorldTransform(current_painter_transform)
            painter.restore()
            if block == self.selected_block:
                painter.save()
                bbox_width_orig = block.bbox[2] - block.bbox[0]
                bbox_height_orig = block.bbox[3] - block.bbox[1]
                unscaled_local_bbox_rect = QRectF(
                    -bbox_width_orig / 2.0,
                    -bbox_height_orig / 2.0,
                    bbox_width_orig,
                    bbox_height_orig,
                )
                painter.setWorldTransform(content_transform, combine=False)
                effective_display_scale_x = (
                    bg_img_to_display_scale_x
                    if bg_img_to_display_scale_x > 0.001
                    else 1.0
                )
                effective_display_scale_y = (
                    bg_img_to_display_scale_y
                    if bg_img_to_display_scale_y > 0.001
                    else 1.0
                )
                effective_display_scale_avg = (
                    effective_display_scale_x + effective_display_scale_y
                ) / 2.0
                selection_pen_width = 2.0 / effective_display_scale_avg
                selection_pen = QPen(QColor(0, 120, 215, 200), selection_pen_width)
                selection_pen.setStyle(Qt.PenStyle.DashLine)
                painter.setPen(selection_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(unscaled_local_bbox_rect)
                painter.setBrush(QColor(0, 120, 215, 200))
                painter.setPen(Qt.PenStyle.NoPen)
                handle_local_w = float(CORNER_HANDLE_SIZE) / effective_display_scale_x
                handle_local_h = float(CORNER_HANDLE_SIZE) / effective_display_scale_y
                corners_local_unscaled = [
                    unscaled_local_bbox_rect.topLeft(),
                    unscaled_local_bbox_rect.topRight(),
                    unscaled_local_bbox_rect.bottomRight(),
                    unscaled_local_bbox_rect.bottomLeft(),
                ]
                for corner_pt_local in corners_local_unscaled:
                    painter.drawRect(
                        QRectF(
                            corner_pt_local.x() - handle_local_w / 2.0,
                            corner_pt_local.y() - handle_local_h / 2.0,
                            handle_local_w,
                            handle_local_h,
                        )
                    )
                rot_handle_offset_local_y = (
                    float(ROTATION_HANDLE_OFFSET) / effective_display_scale_y
                )
                rot_handle_center_x_local = unscaled_local_bbox_rect.center().x()
                rot_handle_center_y_local = (
                    unscaled_local_bbox_rect.top() - rot_handle_offset_local_y
                )
                rot_center_qpointf_local = QPointF(
                    rot_handle_center_x_local, rot_handle_center_y_local
                )
                ellipse_rx_local = handle_local_w / 2.0
                ellipse_ry_local = handle_local_h / 2.0
                painter.drawEllipse(
                    rot_center_qpointf_local, ellipse_rx_local, ellipse_ry_local
                )
                painter.setPen(selection_pen)
                painter.drawLine(
                    QPointF(
                        unscaled_local_bbox_rect.center().x(),
                        unscaled_local_bbox_rect.top(),
                    ),
                    rot_center_qpointf_local,
                )
                painter.restore()
        painter.end()

    def _get_transformed_rect_for_block_interaction(
        self, block: ProcessedBlock
    ) -> tuple[QPolygonF, QRectF, QPointF, QTransform]:
        bg_draw_x, bg_draw_y = 0, 0
        if self.scaled_background_pixmap:
            bg_draw_x = (self.width() - self.scaled_background_pixmap.width()) / 2.0
            bg_draw_y = (self.height() - self.scaled_background_pixmap.height()) / 2.0
        bg_img_to_display_scale_x, bg_img_to_display_scale_y = (
            self._get_bg_fit_scale_factors()
        )
        content_width_orig = block.bbox[2] - block.bbox[0]
        content_height_orig = block.bbox[3] - block.bbox[1]
        if content_width_orig <= 0:
            content_width_orig = 1
        if content_height_orig <= 0:
            content_height_orig = 1
        local_bbox_rect_orig_scale = QRectF(
            -content_width_orig / 2.0,
            -content_height_orig / 2.0,
            content_width_orig,
            content_height_orig,
        )
        block_center_x_orig = (block.bbox[0] + block.bbox[2]) / 2.0
        block_center_y_orig = (block.bbox[1] + block.bbox[3]) / 2.0
        block_display_center_x_rel_bg = block_center_x_orig * bg_img_to_display_scale_x
        block_display_center_y_rel_bg = block_center_y_orig * bg_img_to_display_scale_y
        block_display_center_widget_x = bg_draw_x + block_display_center_x_rel_bg
        block_display_center_widget_y = bg_draw_y + block_display_center_y_rel_bg
        block_display_center_qpoint = QPointF(
            block_display_center_widget_x, block_display_center_widget_y
        )
        transform = QTransform()
        transform.translate(
            block_display_center_widget_x, block_display_center_widget_y
        )
        transform.rotate(block.angle)
        transform.scale(bg_img_to_display_scale_x, bg_img_to_display_scale_y)
        p1 = transform.map(local_bbox_rect_orig_scale.topLeft())
        p2 = transform.map(local_bbox_rect_orig_scale.topRight())
        p3 = transform.map(local_bbox_rect_orig_scale.bottomRight())
        p4 = transform.map(local_bbox_rect_orig_scale.bottomLeft())
        transformed_qpolygon = QPolygonF([p1, p2, p3, p4])
        screen_bounding_rect = transformed_qpolygon.boundingRect()
        return (
            transformed_qpolygon,
            screen_bounding_rect,
            block_display_center_qpoint,
            transform,
        )

    def _get_handle_rects_for_block(
        self, block: ProcessedBlock
    ) -> tuple[list[QRectF], QRectF]:
        _, _, _, effective_transform = self._get_transformed_rect_for_block_interaction(
            block
        )
        content_width_orig = block.bbox[2] - block.bbox[0]
        content_height_orig = block.bbox[3] - block.bbox[1]
        if content_width_orig <= 0:
            content_width_orig = 1
        if content_height_orig <= 0:
            content_height_orig = 1
        local_rect_from_bbox_orig_scale = QRectF(
            -content_width_orig / 2.0,
            -content_height_orig / 2.0,
            content_width_orig,
            content_height_orig,
        )
        handle_sz_view = float(CORNER_HANDLE_SIZE)
        corners_local_orig_scale = [
            local_rect_from_bbox_orig_scale.topLeft(),
            local_rect_from_bbox_orig_scale.topRight(),
            local_rect_from_bbox_orig_scale.bottomRight(),
            local_rect_from_bbox_orig_scale.bottomLeft(),
        ]
        bg_img_to_display_scale_x, bg_img_to_display_scale_y = (
            self._get_bg_fit_scale_factors()
        )
        unscale_x = (
            1.0 / bg_img_to_display_scale_x if bg_img_to_display_scale_x != 0 else 1.0
        )
        unscale_y = (
            1.0 / bg_img_to_display_scale_y if bg_img_to_display_scale_y != 0 else 1.0
        )
        rot_handle_offset_on_screen = float(ROTATION_HANDLE_OFFSET)
        effective_scale_y = (
            bg_img_to_display_scale_y if bg_img_to_display_scale_y > 0.001 else 1.0
        )
        rot_handle_offset_local_y_orig = rot_handle_offset_on_screen / effective_scale_y
        rot_handle_center_local_orig_scale = QPointF(
            local_rect_from_bbox_orig_scale.center().x(),
            local_rect_from_bbox_orig_scale.top() - rot_handle_offset_local_y_orig,
        )
        screen_corner_handle_rects = []
        for pt_local_orig in corners_local_orig_scale:
            screen_pt = effective_transform.map(pt_local_orig)
            screen_corner_handle_rects.append(
                QRectF(
                    screen_pt.x() - handle_sz_view / 2,
                    screen_pt.y() - handle_sz_view / 2,
                    handle_sz_view,
                    handle_sz_view,
                )
            )
        screen_rot_handle_center = effective_transform.map(
            rot_handle_center_local_orig_scale
        )
        screen_rotation_handle_rect = QRectF(
            screen_rot_handle_center.x() - handle_sz_view / 2,
            screen_rot_handle_center.y() - handle_sz_view / 2,
            handle_sz_view,
            handle_sz_view,
        )
        return screen_corner_handle_rects, screen_rotation_handle_rect

    def set_selected_block(self, block: ProcessedBlock | None):
        if self.selected_block != block:
            self.selected_block = block
            self.selection_changed_signal.emit(self.selected_block)
            self.update()

    def mousePressEvent(self, event: QMouseEvent):
        clicked_on_block_or_handle = False
        current_pos_widget = event.position()
        if self.selected_block:
            corner_rects_screen, rot_rect_screen = self._get_handle_rects_for_block(
                self.selected_block
            )
            if rot_rect_screen.contains(current_pos_widget):
                self.rotating_block = True
                self.resizing_block = False
                self.dragging_block = False
                clicked_on_block_or_handle = True
                self.initial_mouse_pos_on_drag = current_pos_widget
                _, _, self.rotation_center_on_rotate, _ = (
                    self._get_transformed_rect_for_block_interaction(
                        self.selected_block
                    )
                )
                self.initial_angle_on_rotate = self.selected_block.angle
                self.setCursor(Qt.CursorShape.CrossCursor)
            else:
                for i, corner_rect_s in enumerate(corner_rects_screen):
                    if corner_rect_s.contains(current_pos_widget):
                        self.resizing_block = True
                        self.rotating_block = False
                        self.dragging_block = False
                        self.resize_corner = i
                        clicked_on_block_or_handle = True
                        self.initial_mouse_pos_on_drag = current_pos_widget
                        self.initial_block_bbox_on_drag = list(self.selected_block.bbox)
                        orig_bbox = self.selected_block.bbox
                        corners_orig_bbox_coords = [
                            QPointF(orig_bbox[0], orig_bbox[1]),
                            QPointF(orig_bbox[2], orig_bbox[1]),
                            QPointF(orig_bbox[2], orig_bbox[3]),
                            QPointF(orig_bbox[0], orig_bbox[3]),
                        ]
                        opposite_corner_idx_map = {0: 2, 1: 3, 2: 0, 3: 1}
                        self.resize_anchor_opposite_corner_orig = (
                            corners_orig_bbox_coords[opposite_corner_idx_map[i]]
                        )
                        self.set_resize_cursor(i, self.selected_block.angle)
                        break
        if not clicked_on_block_or_handle:
            newly_selected_block = None
            for block_item in reversed(self.processed_blocks):
                polygon_screen, _, _, _ = (
                    self._get_transformed_rect_for_block_interaction(block_item)
                )
                if polygon_screen.containsPoint(
                    current_pos_widget, Qt.FillRule.WindingFill
                ):
                    newly_selected_block = block_item
                    break
            if newly_selected_block:
                if self.selected_block != newly_selected_block:
                    self.set_selected_block(newly_selected_block)
                if event.button() == Qt.MouseButton.LeftButton:
                    self.dragging_block = True
                    self.resizing_block = False
                    self.rotating_block = False
                    clicked_on_block_or_handle = True
                    self.initial_mouse_pos_on_drag = current_pos_widget
                    self.initial_block_bbox_on_drag = list(self.selected_block.bbox)
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                if event.button() == Qt.MouseButton.LeftButton:
                    if self.selected_block is not None:
                        self.set_selected_block(None)
                self.dragging_block = False
        if (
            not clicked_on_block_or_handle
            and event.button() == Qt.MouseButton.LeftButton
        ):
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        current_pos_widget = event.position()
        fit_scale_x, fit_scale_y = self._get_bg_fit_scale_factors()
        if (
            self.dragging_block
            and self.selected_block
            and self.initial_block_bbox_on_drag
            and self.initial_mouse_pos_on_drag
        ):
            delta_mouse_screen = current_pos_widget - self.initial_mouse_pos_on_drag
            delta_x_orig = (
                delta_mouse_screen.x() / fit_scale_x if fit_scale_x != 0 else 0
            )
            delta_y_orig = (
                delta_mouse_screen.y() / fit_scale_y if fit_scale_y != 0 else 0
            )
            new_x0 = self.initial_block_bbox_on_drag[0] + delta_x_orig
            new_y0 = self.initial_block_bbox_on_drag[1] + delta_y_orig
            new_x1 = self.initial_block_bbox_on_drag[2] + delta_x_orig
            new_y1 = self.initial_block_bbox_on_drag[3] + delta_y_orig
            self.selected_block.bbox = [new_x0, new_y0, new_x1, new_y1]
            self._invalidate_block_cache(self.selected_block)
            self.block_modified_signal.emit(self.selected_block)
        elif (
            self.rotating_block
            and self.selected_block
            and self.initial_mouse_pos_on_drag
            and self.rotation_center_on_rotate
        ):
            vec_initial = (
                self.initial_mouse_pos_on_drag - self.rotation_center_on_rotate
            )
            vec_current = current_pos_widget - self.rotation_center_on_rotate
            angle_initial_rad = math.atan2(vec_initial.y(), vec_initial.x())
            angle_current_rad = math.atan2(vec_current.y(), vec_current.x())
            delta_angle_rad = angle_current_rad - angle_initial_rad
            delta_angle_deg = math.degrees(delta_angle_rad)
            new_angle = (self.initial_angle_on_rotate + delta_angle_deg) % 360.0
            self.selected_block.angle = new_angle
            self.update()
            self.block_modified_signal.emit(self.selected_block)
        elif (
            self.resizing_block
            and self.selected_block
            and self.initial_block_bbox_on_drag
            and self.initial_mouse_pos_on_drag
            and self.resize_anchor_opposite_corner_orig
        ):
            bg_draw_x, bg_draw_y = 0, 0
            if self.scaled_background_pixmap:
                bg_draw_x = (self.width() - self.scaled_background_pixmap.width()) / 2.0
                bg_draw_y = (
                    self.height() - self.scaled_background_pixmap.height()
                ) / 2.0
            mouse_on_scaled_bg_x = current_pos_widget.x() - bg_draw_x
            mouse_on_scaled_bg_y = current_pos_widget.y() - bg_draw_y
            mouse_on_orig_img_x = (
                mouse_on_scaled_bg_x / fit_scale_x
                if fit_scale_x != 0
                else mouse_on_scaled_bg_x
            )
            mouse_on_orig_img_y = (
                mouse_on_scaled_bg_y / fit_scale_y
                if fit_scale_y != 0
                else mouse_on_scaled_bg_y
            )
            current_mouse_orig = QPointF(mouse_on_orig_img_x, mouse_on_orig_img_y)
            fixed_anchor_x = self.resize_anchor_opposite_corner_orig.x()
            fixed_anchor_y = self.resize_anchor_opposite_corner_orig.y()
            new_x0, new_y0, new_x1, new_y1 = 0.0, 0.0, 0.0, 0.0
            if self.resize_corner == 0:
                new_x0, new_y0 = current_mouse_orig.x(), current_mouse_orig.y()
                new_x1, new_y1 = fixed_anchor_x, fixed_anchor_y
            elif self.resize_corner == 1:
                new_x1, new_y0 = current_mouse_orig.x(), current_mouse_orig.y()
                new_x0, new_y1 = fixed_anchor_x, fixed_anchor_y
            elif self.resize_corner == 2:
                new_x1, new_y1 = current_mouse_orig.x(), current_mouse_orig.y()
                new_x0, new_y0 = fixed_anchor_x, fixed_anchor_y
            elif self.resize_corner == 3:
                new_x0, new_y1 = current_mouse_orig.x(), current_mouse_orig.y()
                new_x1, new_y0 = fixed_anchor_x, fixed_anchor_y
            final_x0 = min(new_x0, new_x1)
            final_x1 = max(new_x0, new_x1)
            final_y0 = min(new_y0, new_y1)
            final_y1 = max(new_y0, new_y1)
            min_bbox_dim_orig = 10
            if final_x1 - final_x0 < min_bbox_dim_orig:
                if self.resize_corner == 0 or self.resize_corner == 3:
                    final_x0 = final_x1 - min_bbox_dim_orig
                else:
                    final_x1 = final_x0 + min_bbox_dim_orig
            if final_y1 - final_y0 < min_bbox_dim_orig:
                if self.resize_corner == 0 or self.resize_corner == 1:
                    final_y0 = final_y1 - min_bbox_dim_orig
                else:
                    final_y1 = final_y0 + min_bbox_dim_orig
            self.selected_block.bbox = [final_x0, final_y0, final_x1, final_y1]
            self._invalidate_block_cache(self.selected_block)
            self.block_modified_signal.emit(self.selected_block)
        else:
            self.update_cursor_on_hover(current_pos_widget)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self.dragging_block = False
        self.resizing_block = False
        self.rotating_block = False
        self.initial_block_bbox_on_drag = None
        self.initial_mouse_pos_on_drag = None
        self.resize_anchor_opposite_corner_orig = None
        self.resize_corner = -1
        self.rotation_center_on_rotate = QPointF()
        self.update_cursor_on_hover(event.position())
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if self.selected_block:
            polygon_screen, _, _, _ = self._get_transformed_rect_for_block_interaction(
                self.selected_block
            )
            if polygon_screen.containsPoint(event.position(), Qt.FillRule.WindingFill):
                dialog = EditableTextDialog(self.selected_block.translated_text, self)
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    new_text = dialog.get_text()
                    if self.selected_block.translated_text != new_text:
                        self.selected_block.translated_text = new_text
                        self._invalidate_block_cache(self.selected_block)
                        self.block_modified_signal.emit(self.selected_block)
                return
        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        event.ignore()

    def _get_bg_fit_scale_factors(self) -> tuple[float, float]:
        if (
            self.scaled_background_pixmap
            and self.background_pixmap
            and self.background_pixmap.width() > 0
            and self.background_pixmap.height() > 0
            and self.scaled_background_pixmap.width() > 0
            and self.scaled_background_pixmap.height() > 0
        ):
            scale_x = (
                self.scaled_background_pixmap.width() / self.background_pixmap.width()
            )
            scale_y = (
                self.scaled_background_pixmap.height() / self.background_pixmap.height()
            )
            return (scale_x, scale_y)
        return 1.0, 1.0

    def update_cursor_on_hover(self, event_pos_widget: QPointF):
        if QApplication.mouseButtons() != Qt.MouseButton.NoButton:
            return
        cursor_set = False
        if self.selected_block:
            corner_rects_s, rot_rect_s = self._get_handle_rects_for_block(
                self.selected_block
            )
            if rot_rect_s.contains(event_pos_widget):
                self.setCursor(Qt.CursorShape.CrossCursor)
                cursor_set = True
            else:
                for i, corner_s_rect in enumerate(corner_rects_s):
                    if corner_s_rect.contains(event_pos_widget):
                        self.set_resize_cursor(i, self.selected_block.angle)
                        cursor_set = True
                        break
        if not cursor_set:
            hovered_block = None
            for block_item in reversed(self.processed_blocks):
                polygon_s, _, _, _ = self._get_transformed_rect_for_block_interaction(
                    block_item
                )
                if polygon_s.containsPoint(event_pos_widget, Qt.FillRule.WindingFill):
                    hovered_block = block_item
                    break
            if hovered_block:
                if hovered_block == self.selected_block:
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
                else:
                    self.setCursor(Qt.CursorShape.PointingHandCursor)
                cursor_set = True
        if not cursor_set:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def set_resize_cursor(self, corner_index: int, angle_degrees: float = 0):
        effective_angle = angle_degrees % 360.0
        if effective_angle < 0:
            effective_angle += 360.0
        if corner_index == 0 or corner_index == 2:
            base_cursor_type = Qt.CursorShape.SizeBDiagCursor
        elif corner_index == 1 or corner_index == 3:
            base_cursor_type = Qt.CursorShape.SizeFDiagCursor
        else:
            base_cursor_type = Qt.CursorShape.ArrowCursor
        if (45 <= effective_angle < 135) or (225 <= effective_angle < 315):
            if base_cursor_type == Qt.CursorShape.SizeFDiagCursor:
                self.setCursor(Qt.CursorShape.SizeBDiagCursor)
            elif base_cursor_type == Qt.CursorShape.SizeBDiagCursor:
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            else:
                self.setCursor(base_cursor_type)
        else:
            self.setCursor(base_cursor_type)

    def contextMenuEvent(self, event: QContextMenuEvent):
        block_under_mouse = None
        for block_item in reversed(self.processed_blocks):
            polygon_screen, _, _, _ = self._get_transformed_rect_for_block_interaction(
                block_item
            )
            if polygon_screen.containsPoint(
                QPointF(event.pos()), Qt.FillRule.WindingFill
            ):
                block_under_mouse = block_item
                break
        menu = QMenu(self)
        if block_under_mouse:
            if self.selected_block != block_under_mouse:
                self.set_selected_block(block_under_mouse)
            edit_action = menu.addAction("编辑文本 (&E)")
            delete_action = menu.addAction("删除文本 (&D)")
            menu.addSeparator()
            orientation_menu = menu.addMenu("文本方向 (&O)")
            set_horiz_action = orientation_menu.addAction("横排")
            set_vert_rtl_action = orientation_menu.addAction("竖排/从右向左")
            set_vert_ltr_action = orientation_menu.addAction("竖排/从左向右")
            current_orientation = getattr(
                self.selected_block, "orientation", "horizontal"
            )
            set_horiz_action.setCheckable(True)
            set_vert_rtl_action.setCheckable(True)
            set_vert_ltr_action.setCheckable(True)
            set_horiz_action.setChecked(current_orientation == "horizontal")
            set_vert_rtl_action.setChecked(current_orientation == "vertical_rtl")
            set_vert_ltr_action.setChecked(current_orientation == "vertical_ltr")
            menu.addSeparator()
            align_menu = menu.addMenu("对齐方式")
            set_align_left_action = align_menu.addAction("左对齐")
            set_align_center_action = align_menu.addAction("居中对齐")
            set_align_right_action = align_menu.addAction("右对齐")
            current_align = getattr(self.selected_block, "text_align", "left")
            set_align_left_action.setCheckable(True)
            set_align_center_action.setCheckable(True)
            set_align_right_action.setCheckable(True)
            set_align_left_action.setChecked(current_align == "left")
            set_align_center_action.setChecked(current_align == "center")
            set_align_right_action.setChecked(current_align == "right")
            menu.addSeparator()
            shape_menu = menu.addMenu("文本形状 (&S)")
            set_box_shape_action = shape_menu.addAction("方框式")
            set_bubble_shape_action = shape_menu.addAction("气泡式")
            current_shape = getattr(self.selected_block, "shape_type", "box")
            set_box_shape_action.setCheckable(True)
            set_bubble_shape_action.setCheckable(True)
            set_box_shape_action.setChecked(current_shape == "box")
            set_bubble_shape_action.setChecked(current_shape == "bubble")
            action = menu.exec(event.globalPos())
            if action == edit_action:
                fake_mouse_event = QMouseEvent(
                    QEvent.Type.MouseButtonDblClick,
                    QPointF(event.pos()),
                    QPointF(event.globalPos()),
                    Qt.MouseButton.LeftButton,
                    Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                )
                self.mouseDoubleClickEvent(fake_mouse_event)
            elif action == delete_action and self.selected_block:
                block_to_delete = self.selected_block
                self.processed_blocks.remove(block_to_delete)
                self._invalidate_block_cache(block_to_delete)
                self.set_selected_block(None)
                self.update()
            elif (
                action in [set_horiz_action, set_vert_rtl_action, set_vert_ltr_action]
                and self.selected_block
            ):
                new_orientation = self.selected_block.orientation
                if action == set_horiz_action:
                    new_orientation = "horizontal"
                elif action == set_vert_rtl_action:
                    new_orientation = "vertical_rtl"
                elif action == set_vert_ltr_action:
                    new_orientation = "vertical_ltr"
                if self.selected_block.orientation != new_orientation:
                    self.selected_block.orientation = new_orientation
                    self._invalidate_block_cache(self.selected_block)
                    self.block_modified_signal.emit(self.selected_block)
            elif (
                action
                in [
                    set_align_left_action,
                    set_align_center_action,
                    set_align_right_action,
                ]
                and self.selected_block
            ):
                new_align = self.selected_block.text_align
                if action == set_align_left_action:
                    new_align = "left"
                elif action == set_align_center_action:
                    new_align = "center"
                elif action == set_align_right_action:
                    new_align = "right"
                if self.selected_block.text_align != new_align:
                    self.selected_block.text_align = new_align
                    self._invalidate_block_cache(self.selected_block)
                    self.block_modified_signal.emit(self.selected_block)
            elif (
                action in [set_box_shape_action, set_bubble_shape_action]
                and self.selected_block
            ):
                new_shape = getattr(self.selected_block, "shape_type", "box")
                if action == set_box_shape_action:
                    new_shape = "box"
                elif action == set_bubble_shape_action:
                    new_shape = "bubble"
                if getattr(self.selected_block, "shape_type", "box") != new_shape:
                    self.selected_block.shape_type = new_shape
                    self._invalidate_block_cache(self.selected_block)
                    self.block_modified_signal.emit(self.selected_block)
        else:
            add_text_action = menu.addAction("新建文本框 (&N)")
            action = menu.exec(event.globalPos())
            if action == add_text_action:
                self._add_new_text_block(QPointF(event.pos()))

    def _add_new_text_block(self, pos_widget: QPointF):
        if not self.background_pixmap:
            QMessageBox.warning(self, "操作无效", "请先加载背景图片才能添加文本框。")
            return
        fit_scale_x, fit_scale_y = self._get_bg_fit_scale_factors()
        if fit_scale_x == 0 or fit_scale_y == 0:
            return
        bg_draw_x, bg_draw_y = 0, 0
        if self.scaled_background_pixmap:
            bg_draw_x = (self.width() - self.scaled_background_pixmap.width()) / 2.0
            bg_draw_y = (self.height() - self.scaled_background_pixmap.height()) / 2.0
        pos_on_scaled_bg_x = pos_widget.x() - bg_draw_x
        pos_on_scaled_bg_y = pos_widget.y() - bg_draw_y
        center_x_orig = pos_on_scaled_bg_x / fit_scale_x
        center_y_orig = pos_on_scaled_bg_y / fit_scale_y
        default_width_orig = 150
        default_height_orig = 50
        default_font_size_category = "medium"
        default_font_size_px = self.font_size_mapping.get(
            default_font_size_category, 22
        )
        fixed_font_size_override = self.config_manager.getint(
            "UI", "fixed_font_size", 0
        )
        if fixed_font_size_override > 0:
            default_font_size_px = fixed_font_size_override
        new_bbox = [
            center_x_orig - default_width_orig / 2,
            center_y_orig - default_height_orig / 2,
            center_x_orig + default_width_orig / 2,
            center_y_orig + default_height_orig / 2,
        ]
        new_id = f"manual_block_{time.time_ns()}_{len(self.processed_blocks)}"
        new_block = ProcessedBlock(
            id=new_id,
            original_text="",
            translated_text="新文本框",
            bbox=new_bbox,
            orientation="horizontal",
            font_size_pixels=default_font_size_px,
            angle=0.0,
            text_align="left",
            font_size_category=default_font_size_category,
        )
        new_block.main_color = None
        new_block.outline_color = None
        new_block.background_color = None
        new_block.outline_thickness = None
        new_block.shape_type = "box"
        self.processed_blocks.append(new_block)
        self._invalidate_block_cache(new_block)
        self.set_selected_block(new_block)
        self.block_modified_signal.emit(new_block)
        self.update()

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self._scale_background_and_view()
