import os
import math
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QFontMetrics, QPen, QBrush
from PyQt6.QtCore import Qt, QRectF, QPointF
from core.config import ConfigManager

try:
    from PIL import Image, ImageDraw, ImageFont as PILImageFont

    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    PILImageFont = None
    Image = None
    ImageDraw = None
    print("警告(utils): Pillow 库未安装，图像处理和显示功能将受限。")
if PILLOW_AVAILABLE:
    from .font import (
        get_pil_font,
        get_font_line_height,
        wrap_text_pil,
        find_font_path,
    )




def pil_to_qpixmap(pil_image: Image.Image) -> QPixmap | None:
    if not PILLOW_AVAILABLE or not pil_image:
        return None
    try:
        if pil_image.mode == "P":
            pil_image = pil_image.convert("RGBA")
        elif pil_image.mode == "L":
            pil_image = pil_image.convert("RGB")
        elif pil_image.mode not in ("RGB", "RGBA"):
            pil_image = pil_image.convert("RGBA")
        data = pil_image.tobytes("raw", pil_image.mode)
        qimage_format = QImage.Format.Format_Invalid
        if pil_image.mode == "RGBA":
            qimage_format = QImage.Format.Format_RGBA8888
        elif pil_image.mode == "RGB":
            qimage_format = QImage.Format.Format_RGB888
        if qimage_format == QImage.Format.Format_Invalid:
            print(
                f"警告(pil_to_qpixmap): 不支持的Pillow图像模式 {pil_image.mode} 转换为QImage。"
            )
            pil_image_rgba = pil_image.convert("RGBA")
            data = pil_image_rgba.tobytes("raw", "RGBA")
            qimage = QImage(
                data,
                pil_image_rgba.width,
                pil_image_rgba.height,
                QImage.Format.Format_RGBA8888,
            )
            if qimage.isNull():
                return None
            return QPixmap.fromImage(qimage)
        qimage = QImage(data, pil_image.width, pil_image.height, qimage_format)
        if qimage.isNull():
            print(
                f"警告(pil_to_qpixmap): QImage.isNull() 为 True，模式: {pil_image.mode}"
            )
            return None
        return QPixmap.fromImage(qimage)
    except Exception as e:
        print(f"错误(pil_to_qpixmap): {e}")
        return None


def crop_image_to_circle(pil_image: Image.Image) -> Image.Image | None:
    if not PILLOW_AVAILABLE or not pil_image:
        return None
    try:
        img = pil_image.copy().convert("RGBA")
        width, height = img.size
        size = min(width, height)
        mask = Image.new("L", (width, height), 0)
        draw_mask = ImageDraw.Draw(mask)
        left = (width - size) // 2
        top = (height - size) // 2
        right = left + size
        bottom = top + size
        draw_mask.ellipse((left, top, right, bottom), fill=255)
        output_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        output_img.paste(img, (0, 0), mask=mask)
        return output_img
    except Exception as e:
        print(f"错误(crop_image_to_circle): {e}")
        return None


def check_dependencies_availability():
    dependencies = {
        "Pillow": PILLOW_AVAILABLE,
        "google.generativeai": False,
        "google-cloud-vision_lib_present": False,
        "openai_lib": False,
    }
    try:
        import google.generativeai

        dependencies["google.generativeai"] = True
    except ImportError:
        pass
    try:
        import google.cloud.vision

        dependencies["google-cloud-vision_lib_present"] = True
    except ImportError:
        pass
    try:
        import openai

        dependencies["openai_lib"] = True
    except ImportError:
        pass
    return dependencies


def _render_single_block_pil_for_preview(
    block: "ProcessedBlock",
    font_name_config: str,
    text_main_color_pil: tuple,
    text_outline_color_pil: tuple,
    text_bg_color_pil: tuple,
    outline_thickness: int,
    text_padding: int,
    h_char_spacing_px: int,
    h_line_spacing_px: int,
    v_char_spacing_px: int,
    v_col_spacing_px: int,
    h_manual_break_extra_px: int = 0,
    v_manual_break_extra_px: int = 0,
) -> Image.Image | None:
    if (
        not PILLOW_AVAILABLE
        or not block.translated_text
        or not block.translated_text.strip()
    ):
        if PILLOW_AVAILABLE and block.bbox:
            bbox_width = int(block.bbox[2] - block.bbox[0])
            bbox_height = int(block.bbox[3] - block.bbox[1])
            if bbox_width > 0 and bbox_height > 0:
                empty_surface = Image.new(
                    "RGBA", (bbox_width, bbox_height), (0, 0, 0, 0)
                )
                if (
                    text_bg_color_pil
                    and len(text_bg_color_pil) == 4
                    and text_bg_color_pil[3] > 0
                ):
                    shape_type = getattr(block, "shape_type", "box")
                    draw = ImageDraw.Draw(empty_surface)
                    if shape_type == "bubble":
                        draw.ellipse(
                            [(0, 0), (bbox_width - 1, bbox_height - 1)],
                            fill=text_bg_color_pil,
                        )
                    else:
                        draw.rectangle(
                            [(0, 0), (bbox_width - 1, bbox_height - 1)],
                            fill=text_bg_color_pil,
                        )
                return empty_surface
        return None
    font_size_to_use = int(block.font_size_pixels)
    pil_font = get_pil_font(font_name_config, font_size_to_use)
    if not pil_font:
        print(
            f"警告(_render_single_block_pil_for_preview): 无法加载字体 '{font_name_config}' (大小: {font_size_to_use}px)"
        )
        bbox_w_err = int(block.bbox[2] - block.bbox[0]) if block.bbox else 100
        bbox_h_err = int(block.bbox[3] - block.bbox[1]) if block.bbox else 50
        err_img = Image.new(
            "RGBA", (max(1, bbox_w_err), max(1, bbox_h_err)), (255, 0, 0, 100)
        )
        ImageDraw.Draw(err_img).text(
            (5, 5),
            "字体错误",
            font=PILImageFont.load_default(),
            fill=(255, 255, 255, 255),
        )
        return err_img
    text_to_draw = block.translated_text
    dummy_metric_img = Image.new("RGBA", (1, 1))
    pil_draw_metric = ImageDraw.Draw(dummy_metric_img)
    target_surface_width = int(block.bbox[2] - block.bbox[0])
    target_surface_height = int(block.bbox[3] - block.bbox[1])
    if target_surface_width <= 0 or target_surface_height <= 0:
        print(
            f"警告(_render_single_block_pil_for_preview): block.bbox '{block.bbox}' 尺寸无效。"
        )
        err_img_bbox = Image.new("RGBA", (100, 50), (255, 0, 0, 100))
        ImageDraw.Draw(err_img_bbox).text(
            (5, 5),
            "BBox错误",
            font=PILImageFont.load_default(),
            fill=(255, 255, 255, 255),
        )
        return err_img_bbox
    max_content_width_for_wrapping = max(1, target_surface_width - (2 * text_padding))
    max_content_height_for_wrapping = max(1, target_surface_height - (2 * text_padding))
    
    # For bubble (ellipse) shapes, reduce available space to prevent text overflow at edges
    # A rectangle inscribed in an ellipse has max area when sides are sqrt(2) smaller than axes
    # Factor 0.707 is the theoretical limit, using 0.75 as a practical compromise for visual balance
    # (Text doesn't usually fill the very corners of the wrapping box)
    shape_type = getattr(block, "shape_type", "box")
    bubble_offset_x = 0
    bubble_offset_y = 0
    if shape_type == "bubble":
        original_w = max_content_width_for_wrapping
        original_h = max_content_height_for_wrapping
        # Use 0.75 to keep it reasonably large but safe enough for most text
        scale_factor = 0.75
        max_content_width_for_wrapping = int(original_w * scale_factor)
        max_content_height_for_wrapping = int(original_h * scale_factor)
        # Calculate offset to keep the reduced box centered
        bubble_offset_x = (original_w - max_content_width_for_wrapping) / 2.0
        bubble_offset_y = (original_h - max_content_height_for_wrapping) / 2.0
    
    wrapped_segments: list[str]
    actual_text_render_width_unpadded: int
    actual_text_render_height_unpadded: int
    seg_secondary_dim_with_spacing: int
    if block.orientation == "horizontal":
        (
            wrapped_segments,
            actual_text_render_height_unpadded,
            seg_secondary_dim_with_spacing,
            actual_text_render_width_unpadded,
        ) = wrap_text_pil(
            pil_draw_metric,
            text_to_draw,
            pil_font,
            max_dim=int(max_content_width_for_wrapping),
            orientation="horizontal",
            char_spacing_px=h_char_spacing_px,
            line_or_col_spacing_px=h_line_spacing_px,
        )
    else:
        (
            wrapped_segments,
            actual_text_render_width_unpadded,
            seg_secondary_dim_with_spacing,
            actual_text_render_height_unpadded,
        ) = wrap_text_pil(
            pil_draw_metric,
            text_to_draw,
            pil_font,
            max_dim=int(max_content_height_for_wrapping),
            orientation="vertical",
            char_spacing_px=v_char_spacing_px,
            line_or_col_spacing_px=v_col_spacing_px,
        )
    if not wrapped_segments and text_to_draw:
        wrapped_segments = [text_to_draw]
        if block.orientation == "horizontal":
            actual_text_render_width_unpadded = pil_draw_metric.textlength(
                text_to_draw, font=pil_font
            ) + (
                h_char_spacing_px * (len(text_to_draw) - 1)
                if len(text_to_draw) > 1
                else 0
            )
            seg_secondary_dim_with_spacing = get_font_line_height(
                pil_font, font_size_to_use, h_line_spacing_px
            )
            actual_text_render_height_unpadded = seg_secondary_dim_with_spacing
        else:
            try:
                actual_text_render_width_unpadded = pil_font.getlength("M")
            except:
                actual_text_render_width_unpadded = font_size_to_use
            seg_secondary_dim_with_spacing = get_font_line_height(
                pil_font, font_size_to_use, v_char_spacing_px
            )
            actual_text_render_height_unpadded = (
                len(text_to_draw) * seg_secondary_dim_with_spacing
            )
    if (
        not wrapped_segments
        or (
            actual_text_render_width_unpadded <= 0
            or actual_text_render_height_unpadded <= 0
        )
        and text_to_draw
    ):
        if text_to_draw:
            print(
                f"警告(_render_single_block_pil_for_preview): 文本 '{text_to_draw[:20]}...' 的计算渲染尺寸为零或负。"
            )
        empty_surface_fallback = Image.new(
            "RGBA", (target_surface_width, target_surface_height), (0, 0, 0, 0)
        )
        if (
            text_bg_color_pil
            and len(text_bg_color_pil) == 4
            and text_bg_color_pil[3] > 0
        ):
            shape_type = getattr(block, "shape_type", "box")
            draw_fallback = ImageDraw.Draw(empty_surface_fallback)
            if shape_type == "bubble":
                draw_fallback.ellipse(
                    [(0, 0), (target_surface_width - 1, target_surface_height - 1)],
                    fill=text_bg_color_pil,
                )
            else:
                draw_fallback.rectangle(
                    [(0, 0), (target_surface_width - 1, target_surface_height - 1)],
                    fill=text_bg_color_pil,
                )
        return empty_surface_fallback
    block_surface = Image.new(
        "RGBA", (target_surface_width, target_surface_height), (0, 0, 0, 0)
    )
    draw_on_block_surface = ImageDraw.Draw(block_surface)
    if text_bg_color_pil and len(text_bg_color_pil) == 4 and text_bg_color_pil[3] > 0:
        shape_type = getattr(block, "shape_type", "box")
        if shape_type == "bubble":
            # Draw ellipse background for bubble style
            draw_on_block_surface.ellipse(
                [(0, 0), (target_surface_width - 1, target_surface_height - 1)],
                fill=text_bg_color_pil,
            )
        else:
            # Draw rectangle background for box style (default)
            draw_on_block_surface.rectangle(
                [(0, 0), (target_surface_width - 1, target_surface_height - 1)],
                fill=text_bg_color_pil,
            )
    content_area_x_start = text_padding + bubble_offset_x
    content_area_y_start = text_padding + bubble_offset_y
    text_block_overall_start_x = content_area_x_start
    text_block_overall_start_y = content_area_y_start
    if block.orientation == "horizontal":
        if block.text_align == "center":
            text_block_overall_start_x = (
                content_area_x_start
                + (max_content_width_for_wrapping - actual_text_render_width_unpadded)
                / 2.0
            )
        elif block.text_align == "right":
            text_block_overall_start_x = (
                content_area_x_start
                + max_content_width_for_wrapping
                - actual_text_render_width_unpadded
            )
    else:
        if block.text_align == "center":
            text_block_overall_start_x = (
                content_area_x_start
                + (max_content_width_for_wrapping - actual_text_render_width_unpadded)
                / 2.0
            )
        elif block.text_align == "right":
            text_block_overall_start_x = (
                content_area_x_start
                + max_content_width_for_wrapping
                - actual_text_render_width_unpadded
            )
    if block.orientation == "horizontal":
        current_y_pil = text_block_overall_start_y
        for line_idx, line_text in enumerate(wrapped_segments):
            is_manual_break_line = line_text == ""
            if not is_manual_break_line:
                line_w_specific_pil = pil_draw_metric.textlength(
                    line_text, font=pil_font
                )
                if len(line_text) > 1 and h_char_spacing_px != 0:
                    line_w_specific_pil += h_char_spacing_px * (len(line_text) - 1)
                line_draw_x_pil = text_block_overall_start_x
                if block.text_align == "center":
                    line_draw_x_pil = (
                        text_block_overall_start_x
                        + (actual_text_render_width_unpadded - line_w_specific_pil)
                        / 2.0
                    )
                elif block.text_align == "right":
                    line_draw_x_pil = text_block_overall_start_x + (
                        actual_text_render_width_unpadded - line_w_specific_pil
                    )
                if (
                    outline_thickness > 0
                    and text_outline_color_pil
                    and len(text_outline_color_pil) == 4
                    and text_outline_color_pil[3] > 0
                ):
                    for dx_o in range(-outline_thickness, outline_thickness + 1):
                        for dy_o in range(-outline_thickness, outline_thickness + 1):
                            if dx_o == 0 and dy_o == 0:
                                continue
                            if h_char_spacing_px != 0:
                                temp_x_char_outline = line_draw_x_pil + dx_o
                                for char_ol in line_text:
                                    draw_on_block_surface.text(
                                        (temp_x_char_outline, current_y_pil + dy_o),
                                        char_ol,
                                        font=pil_font,
                                        fill=text_outline_color_pil,
                                    )
                                    temp_x_char_outline += (
                                        pil_draw_metric.textlength(
                                            char_ol, font=pil_font
                                        )
                                        + h_char_spacing_px
                                    )
                            else:
                                draw_on_block_surface.text(
                                    (line_draw_x_pil + dx_o, current_y_pil + dy_o),
                                    line_text,
                                    font=pil_font,
                                    fill=text_outline_color_pil,
                                    spacing=0,
                                )
                if h_char_spacing_px != 0:
                    temp_x_char_main = line_draw_x_pil
                    for char_m in line_text:
                        draw_on_block_surface.text(
                            (temp_x_char_main, current_y_pil),
                            char_m,
                            font=pil_font,
                            fill=text_main_color_pil,
                        )
                        temp_x_char_main += (
                            pil_draw_metric.textlength(char_m, font=pil_font)
                            + h_char_spacing_px
                        )
                else:
                    draw_on_block_surface.text(
                        (line_draw_x_pil, current_y_pil),
                        line_text,
                        font=pil_font,
                        fill=text_main_color_pil,
                        spacing=0,
                    )
            current_y_pil += seg_secondary_dim_with_spacing
            if is_manual_break_line:
                current_y_pil += h_manual_break_extra_px
    else:
        try:
            single_col_visual_width_metric = pil_font.getlength("M")
            if single_col_visual_width_metric == 0:
                single_col_visual_width_metric = (
                    pil_font.size if hasattr(pil_font, "size") else font_size_to_use
                )
        except AttributeError:
            single_col_visual_width_metric = (
                pil_font.size if hasattr(pil_font, "size") else font_size_to_use
            )
        current_x_pil_col_draw_start = 0.0
        if block.orientation == "vertical_rtl":
            current_x_pil_col_draw_start = (
                text_block_overall_start_x
                + actual_text_render_width_unpadded
                - single_col_visual_width_metric
            )
        else:
            current_x_pil_col_draw_start = text_block_overall_start_x
        current_y_pil_char_start = text_block_overall_start_y
        
        # Define characters that need rotation in vertical text
        VERTICAL_ROTATION_CHARS = {
            "…", "—", "–", "-", "_", 
            "(", ")", "[", "]", "{", "}", "<", ">",
            "（", "）", "【", "】", "《", "》", "「", "」", "『", "』", "〈", "〉",
            "～", "〜"
        }
        
        for col_idx, col_text in enumerate(wrapped_segments):
            is_manual_break_col = col_text == ""
            current_y_pil_char = current_y_pil_char_start
            if not is_manual_break_col:
                for char_in_col_idx, char_in_col in enumerate(col_text):
                    char_w_specific_pil = pil_draw_metric.textlength(
                        char_in_col, font=pil_font
                    )
                    char_x_offset_in_col_slot = (
                        single_col_visual_width_metric - char_w_specific_pil
                    ) / 2.0
                    final_char_draw_x = (
                        current_x_pil_col_draw_start + char_x_offset_in_col_slot
                    )
                    
                    # Check if character needs rotation
                    if char_in_col in VERTICAL_ROTATION_CHARS:
                        # Create a small image for the character to rotate it
                        # Use a slightly larger box to avoid clipping during rotation
                        char_img_size = int(font_size_to_use * 1.5)
                        char_img = Image.new("RGBA", (char_img_size, char_img_size), (0, 0, 0, 0))
                        char_draw = ImageDraw.Draw(char_img)
                        
                        # Draw char centered precisely using textbbox
                        # 1. Get bbox of the char
                        left, top, right, bottom = char_draw.textbbox((0, 0), char_in_col, font=pil_font)
                        char_w_real = right - left
                        char_h_real = bottom - top
                        
                        # 2. Calculate position to center the bbox in the image
                        # We want the center of the bbox ((left+right)/2, (top+bottom)/2) to be at (char_img_size/2, char_img_size/2)
                        
                        bbox_center_x = (left + right) / 2
                        bbox_center_y = (top + bottom) / 2
                        
                        target_center_x = char_img_size / 2
                        target_center_y = char_img_size / 2
                        
                        draw_x = target_center_x - bbox_center_x
                        draw_y = target_center_y - bbox_center_y
                        
                        # Draw outline if needed
                        if (
                            outline_thickness > 0
                            and text_outline_color_pil
                            and len(text_outline_color_pil) == 4
                            and text_outline_color_pil[3] > 0
                        ):
                             for dx_o in range(-outline_thickness, outline_thickness + 1):
                                for dy_o in range(-outline_thickness, outline_thickness + 1):
                                    if dx_o == 0 and dy_o == 0:
                                        continue
                                    char_draw.text(
                                        (draw_x + dx_o, draw_y + dy_o),
                                        char_in_col,
                                        font=pil_font,
                                        fill=text_outline_color_pil,
                                    )
                        
                        # Draw main text
                        char_draw.text(
                            (draw_x, draw_y),
                            char_in_col,
                            font=pil_font,
                            fill=text_main_color_pil,
                        )
                        
                        # Rotate 90 degrees clockwise
                        rotated_char_img = char_img.rotate(-90, resample=Image.Resampling.BICUBIC)
                        
                        # Calculate paste position (centering in the slot)
                        slot_center_x = current_x_pil_col_draw_start + single_col_visual_width_metric / 2
                        
                        paste_x = int(slot_center_x - char_img_size / 2)
                        paste_y = int(current_y_pil_char + (seg_secondary_dim_with_spacing - char_img_size) / 2)
                        
                        block_surface.alpha_composite(rotated_char_img, (paste_x, paste_y))
                        
                    else:
                        # Normal drawing for non-rotated characters
                        if (
                            outline_thickness > 0
                            and text_outline_color_pil
                            and len(text_outline_color_pil) == 4
                            and text_outline_color_pil[3] > 0
                        ):
                            for dx_o in range(-outline_thickness, outline_thickness + 1):
                                for dy_o in range(
                                    -outline_thickness, outline_thickness + 1
                                ):
                                    if dx_o == 0 and dy_o == 0:
                                        continue
                                    draw_on_block_surface.text(
                                        (
                                            final_char_draw_x + dx_o,
                                            current_y_pil_char + dy_o,
                                        ),
                                        char_in_col,
                                        font=pil_font,
                                        fill=text_outline_color_pil,
                                    )
                        draw_on_block_surface.text(
                            (final_char_draw_x, current_y_pil_char),
                            char_in_col,
                            font=pil_font,
                            fill=text_main_color_pil,
                        )
                    current_y_pil_char += seg_secondary_dim_with_spacing
            if col_idx < len(wrapped_segments) - 1:
                spacing_for_next_column = (
                    single_col_visual_width_metric + v_col_spacing_px
                )
                if is_manual_break_col:
                    spacing_for_next_column += v_manual_break_extra_px
                if block.orientation == "vertical_rtl":
                    current_x_pil_col_draw_start -= spacing_for_next_column
                else:
                    current_x_pil_col_draw_start += spacing_for_next_column
    return block_surface


def _draw_single_block_pil(
    draw_target_image: Image.Image,
    block: "ProcessedBlock",
    font_name_config: str,
    text_main_color_pil: tuple,
    text_outline_color_pil: tuple,
    text_bg_color_pil: tuple,
    outline_thickness: int,
    text_padding: int,
    h_char_spacing_px: int,
    h_line_spacing_px: int,
    v_char_spacing_px: int,
    v_col_spacing_px: int,
    h_manual_break_extra_px: int = 0,
    v_manual_break_extra_px: int = 0,
) -> None:
    if (
        not PILLOW_AVAILABLE
        or not block.translated_text
        or not block.translated_text.strip()
    ):
        return
    rendered_block_content_pil = _render_single_block_pil_for_preview(
        block=block,
        font_name_config=font_name_config,
        text_main_color_pil=text_main_color_pil,
        text_outline_color_pil=text_outline_color_pil,
        text_bg_color_pil=text_bg_color_pil,
        outline_thickness=outline_thickness,
        text_padding=text_padding,
        h_char_spacing_px=h_char_spacing_px,
        h_line_spacing_px=h_line_spacing_px,
        v_char_spacing_px=v_char_spacing_px,
        v_col_spacing_px=v_col_spacing_px,
        h_manual_break_extra_px=h_manual_break_extra_px,
        v_manual_break_extra_px=v_manual_break_extra_px,
    )
    if not rendered_block_content_pil:
        return
    final_surface_to_paste = rendered_block_content_pil
    if block.angle != 0:
        try:
            final_surface_to_paste = rendered_block_content_pil.rotate(
                -block.angle, expand=True, resample=Image.Resampling.BICUBIC
            )
        except Exception as e:
            print(f"Error rotating block content: {e}")
    block_center_x_orig_coords = (block.bbox[0] + block.bbox[2]) / 2.0
    block_center_y_orig_coords = (block.bbox[1] + block.bbox[3]) / 2.0
    paste_x = int(
        round(block_center_x_orig_coords - (final_surface_to_paste.width / 2.0))
    )
    paste_y = int(
        round(block_center_y_orig_coords - (final_surface_to_paste.height / 2.0))
    )
    if draw_target_image.mode != "RGBA":
        print(
            f"Warning (_draw_single_block_pil): draw_target_image is not RGBA (mode: {draw_target_image.mode}). Alpha compositing might not work as expected."
        )
    try:
        if final_surface_to_paste.mode == "RGBA":
            draw_target_image.alpha_composite(
                final_surface_to_paste, (paste_x, paste_y)
            )
        else:
            draw_target_image.paste(final_surface_to_paste, (paste_x, paste_y))
    except Exception as e:
        print(
            f"Error compositing/pasting block '{block.translated_text[:20]}...' onto target image: {e}"
        )
        try:
            if final_surface_to_paste.mode == "RGBA":
                draw_target_image.paste(
                    final_surface_to_paste,
                    (paste_x, paste_y),
                    mask=final_surface_to_paste,
                )
            else:
                draw_target_image.paste(final_surface_to_paste, (paste_x, paste_y))
        except Exception as e_paste:
            print(f"Fallback paste also failed for block: {e_paste}")


def draw_processed_blocks_pil(
    pil_image_original,
    processed_blocks,
    config_manager,
):
    if not PILLOW_AVAILABLE or not pil_image_original:
        print("Warning (draw_processed_blocks_pil): Pillow not available or no original image.")
        return pil_image_original
    if not processed_blocks:
        return pil_image_original.copy() if pil_image_original else None
    try:
        if pil_image_original.mode != "RGBA":
            base_image = pil_image_original.convert("RGBA")
        else:
            base_image = pil_image_original.copy()
        font_name_conf = config_manager.get("UI", "font_name", "msyh.ttc")
        text_pad_conf = config_manager.getint("UI", "text_padding", 3)
        main_color_str = config_manager.get("UI", "text_main_color", "255,255,255,255")
        outline_color_str = config_manager.get("UI", "text_outline_color", "0,0,0,255")
        outline_thick_conf_default = config_manager.getint("UI", "text_outline_thickness", 2)
        bg_color_str = config_manager.get("UI", "text_background_color", "0,0,0,128")
        h_char_spacing_conf = config_manager.getint("UI", "h_text_char_spacing_px", 0)
        h_line_spacing_conf = config_manager.getint("UI", "h_text_line_spacing_px", 0)
        v_char_spacing_conf = config_manager.getint("UI", "v_text_char_spacing_px", 0)
        v_col_spacing_conf = config_manager.getint("UI", "v_text_column_spacing_px", 0)
        h_manual_break_extra_conf = config_manager.getint("UI", "h_manual_break_extra_spacing_px", 0)
        v_manual_break_extra_conf = config_manager.getint("UI", "v_manual_break_extra_spacing_px", 0)

        def _parse_color(color_string, default_rgba):
            try:
                parts = list(map(int, color_string.split(",")))
                if len(parts) == 3:
                    return tuple(parts) + (255,)
                if len(parts) == 4:
                    return tuple(parts)
            except:
                pass
            return default_rgba

        default_main_color_pil = _parse_color(main_color_str, (255, 255, 255, 255))
        default_outline_color_pil = _parse_color(outline_color_str, (0, 0, 0, 255))
        default_bg_color_pil = _parse_color(bg_color_str, (0, 0, 0, 128))
        
        for idx, block_item in enumerate(processed_blocks):
            if not hasattr(block_item, "translated_text") or not block_item.translated_text or not block_item.translated_text.strip():
                continue
            if not hasattr(block_item, "bbox") or not block_item.bbox or len(block_item.bbox) != 4:
                continue
            if not hasattr(block_item, "font_size_pixels") or not block_item.font_size_pixels or block_item.font_size_pixels <= 0:
                continue
                
            main_color_to_use = default_main_color_pil
            if hasattr(block_item, "main_color") and block_item.main_color is not None:
                if isinstance(block_item.main_color, tuple) and len(block_item.main_color) == 4:
                    main_color_to_use = block_item.main_color
                    
            outline_color_to_use = default_outline_color_pil
            if hasattr(block_item, "outline_color") and block_item.outline_color is not None:
                if isinstance(block_item.outline_color, tuple) and len(block_item.outline_color) == 4:
                    outline_color_to_use = block_item.outline_color
                    
            bg_color_to_use = default_bg_color_pil
            if hasattr(block_item, "background_color") and block_item.background_color is not None:
                if isinstance(block_item.background_color, tuple) and len(block_item.background_color) == 4:
                    bg_color_to_use = block_item.background_color
                    
            thickness_to_use = outline_thick_conf_default
            if hasattr(block_item, "outline_thickness") and block_item.outline_thickness is not None:
                if isinstance(block_item.outline_thickness, int) and block_item.outline_thickness >= 0:
                    thickness_to_use = block_item.outline_thickness
                    
            _draw_single_block_pil(
                draw_target_image=base_image,
                block=block_item,
                font_name_config=font_name_conf,
                text_main_color_pil=main_color_to_use,
                text_outline_color_pil=outline_color_to_use,
                text_bg_color_pil=bg_color_to_use,
                outline_thickness=thickness_to_use,
                text_padding=text_pad_conf,
                h_char_spacing_px=h_char_spacing_conf,
                h_line_spacing_px=h_line_spacing_conf,
                v_char_spacing_px=v_char_spacing_conf,
                v_col_spacing_px=v_col_spacing_conf,
                h_manual_break_extra_px=h_manual_break_extra_conf,
                v_manual_break_extra_px=v_manual_break_extra_conf,
            )
        return base_image
    except Exception as e:
        print(f"严重错误 (draw_processed_blocks_pil): {e}")
        import traceback
        traceback.print_exc()
        return pil_image_original


def _draw_single_block_pil(
    draw_target_image,
    block,
    font_name_config,
    text_main_color_pil,
    text_outline_color_pil,
    text_bg_color_pil,
    outline_thickness,
    text_padding,
    h_char_spacing_px,
    h_line_spacing_px,
    v_char_spacing_px,
    v_col_spacing_px,
    h_manual_break_extra_px=0,
    v_manual_break_extra_px=0,
):
    if not PILLOW_AVAILABLE or not block.translated_text or not block.translated_text.strip():
        return
    rendered_block_content_pil = _render_single_block_pil_for_preview(
        block=block,
        font_name_config=font_name_config,
        text_main_color_pil=text_main_color_pil,
        text_outline_color_pil=text_outline_color_pil,
        text_bg_color_pil=text_bg_color_pil,
        outline_thickness=outline_thickness,
        text_padding=text_padding,
        h_char_spacing_px=h_char_spacing_px,
        h_line_spacing_px=h_line_spacing_px,
        v_char_spacing_px=v_char_spacing_px,
        v_col_spacing_px=v_col_spacing_px,
        h_manual_break_extra_px=h_manual_break_extra_px,
        v_manual_break_extra_px=v_manual_break_extra_px,
    )
    if not rendered_block_content_pil:
        return
    final_surface_to_paste = rendered_block_content_pil
    if block.angle != 0:
        try:
            final_surface_to_paste = rendered_block_content_pil.rotate(
                -block.angle, expand=True, resample=Image.Resampling.BICUBIC
            )
        except Exception as e:
            print(f"Error rotating block content: {e}")
    block_center_x_orig_coords = (block.bbox[0] + block.bbox[2]) / 2.0
    block_center_y_orig_coords = (block.bbox[1] + block.bbox[3]) / 2.0
    paste_x = int(round(block_center_x_orig_coords - (final_surface_to_paste.width / 2.0)))
    paste_y = int(round(block_center_y_orig_coords - (final_surface_to_paste.height / 2.0)))
    try:
        if final_surface_to_paste.mode == "RGBA":
            draw_target_image.alpha_composite(final_surface_to_paste, (paste_x, paste_y))
        else:
            draw_target_image.paste(final_surface_to_paste, (paste_x, paste_y))
    except Exception as e_paste:
        print(f"Error pasting block: {e_paste}")
