"""
功能22：后端 ReportLab PDF 行程册生成服务

采用内置 CIDFont（STSong-Light）支持中文，无需额外字体文件。
生成包含封面、预算明细、每日行程（景点/餐饮/住宿）的结构化 PDF。
"""
import io
from datetime import datetime
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from ..models.schemas import TripPlan

# ── 注册内置 CJK 字体（无需额外字体文件）──────────────────────────────────
pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
CN_FONT = "STSong-Light"

# ── 页面尺寸与边距 ────────────────────────────────────────────────────────
PAGE_W, PAGE_H = A4
MARGIN = 2 * cm

# ── 颜色常量 ─────────────────────────────────────────────────────────────
COLOR_PRIMARY = colors.HexColor("#1677ff")   # Ant Design blue
COLOR_ACCENT = colors.HexColor("#52c41a")    # green
COLOR_WARN = colors.HexColor("#fa8c16")      # orange
COLOR_HEADER_BG = colors.HexColor("#e6f4ff")
COLOR_ROW_ALT = colors.HexColor("#fafafa")
COLOR_BORDER = colors.HexColor("#d9d9d9")


def _build_styles() -> dict:
    """构建中文段落样式字典"""
    base = getSampleStyleSheet()
    def cn(name, **kw) -> ParagraphStyle:
        return ParagraphStyle(name, fontName=CN_FONT, **kw)

    return {
        "cover_title": cn("cover_title", fontSize=28, leading=36,
                          alignment=TA_CENTER, textColor=COLOR_PRIMARY, spaceAfter=8),
        "cover_sub":   cn("cover_sub",   fontSize=14, leading=20,
                          alignment=TA_CENTER, textColor=colors.grey, spaceAfter=4),
        "cover_meta":  cn("cover_meta",  fontSize=11, leading=16,
                          alignment=TA_CENTER, spaceAfter=2),
        "section":     cn("section",     fontSize=15, leading=20,
                          textColor=COLOR_PRIMARY, spaceBefore=14, spaceAfter=6),
        "day_header":  cn("day_header",  fontSize=13, leading=18,
                          textColor=colors.white, backColor=COLOR_PRIMARY,
                          spaceBefore=10, spaceAfter=4),
        "body":        cn("body",        fontSize=10, leading=14, spaceAfter=3),
        "hint":        cn("hint",        fontSize=9,  leading=12,
                          textColor=colors.grey, spaceAfter=2),
        "footer":      cn("footer",      fontSize=8,  alignment=TA_CENTER,
                          textColor=colors.lightgrey),
    }


def _header_footer(canvas, doc):
    """每页页眉/页脚回调"""
    canvas.saveState()
    # 页眉
    canvas.setFont(CN_FONT, 8)
    canvas.setFillColor(colors.grey)
    canvas.drawString(MARGIN, PAGE_H - 1.2 * cm, "HelloAgents 旅行规划平台")
    canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 1.2 * cm,
                           f"生成时间：{datetime.now().strftime('%Y-%m-%d')}")
    canvas.line(MARGIN, PAGE_H - 1.4 * cm, PAGE_W - MARGIN, PAGE_H - 1.4 * cm)
    # 页脚
    canvas.line(MARGIN, 1.4 * cm, PAGE_W - MARGIN, 1.4 * cm)
    canvas.drawCentredString(PAGE_W / 2, 0.8 * cm, f"- {doc.page} -")
    canvas.restoreState()


def _meal_type_label(t: str) -> str:
    return {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐",
            "snack": "小吃/下午茶"}.get(t, t)


def _table_style(header_bg=COLOR_HEADER_BG) -> TableStyle:
    return TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0),  header_bg),
        ("TEXTCOLOR",    (0, 0), (-1, 0),  COLOR_PRIMARY),
        ("FONTNAME",     (0, 0), (-1, -1), CN_FONT),
        ("FONTSIZE",     (0, 0), (-1, -1), 9),
        ("LEADING",      (0, 0), (-1, -1), 13),
        ("GRID",         (0, 0), (-1, -1), 0.4, COLOR_BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLOR_ROW_ALT]),
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ])


def generate_trip_pdf(plan: TripPlan) -> bytes:
    """
    将 TripPlan 序列化为 PDF 字节流。

    Args:
        plan: 完整行程计划数据

    Returns:
        PDF 文件字节内容（bytes）
    """
    buf = io.BytesIO()
    doc = BaseDocTemplate(
        buf, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=2 * cm, bottomMargin=2 * cm,
    )

    frame = Frame(MARGIN, 1.8 * cm, PAGE_W - 2 * MARGIN, PAGE_H - 3.8 * cm, id="normal")
    tmpl = PageTemplate(id="main", frames=[frame], onPage=_header_footer)
    doc.addPageTemplates([tmpl])

    S = _build_styles()
    story = []

    # ── 封面 ─────────────────────────────────────────────────────────────
    story.append(Spacer(1, 3 * cm))
    story.append(Paragraph(f"✈ {plan.city} 旅行计划", S["cover_title"]))
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph(f"{plan.start_date}  →  {plan.end_date}", S["cover_sub"]))
    story.append(Paragraph(f"共 {plan.travel_days if hasattr(plan, 'travel_days') else len(plan.days)} 天  ·  {len(plan.days)} 日行程", S["cover_meta"]))
    story.append(Spacer(1, 0.8 * cm))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_PRIMARY))
    story.append(Spacer(1, 0.6 * cm))

    if plan.overall_suggestions:
        story.append(Paragraph("📌 总体建议", S["section"]))
        story.append(Paragraph(plan.overall_suggestions, S["body"]))
        story.append(Spacer(1, 0.4 * cm))

    # ── 预算明细 ──────────────────────────────────────────────────────────
    if plan.budget:
        b = plan.budget
        story.append(Paragraph("💰 预算明细", S["section"]))
        budget_data = [
            ["项目", "金额（元）"],
            ["景点门票",  f"¥ {b.total_attractions:,}"],
            ["住宿费用",  f"¥ {b.total_hotels:,}"],
            ["餐饮费用",  f"¥ {b.total_meals:,}"],
            ["交通费用",  f"¥ {b.total_transportation:,}"],
            ["合计总费用", f"¥ {b.total:,}"],
        ]
        t = Table(budget_data, colWidths=[10 * cm, 5 * cm])
        ts = _table_style()
        ts.add("FONTNAME", (0, len(budget_data) - 1), (-1, -1), CN_FONT)
        ts.add("BACKGROUND", (0, len(budget_data) - 1), (-1, -1), COLOR_ACCENT)
        ts.add("TEXTCOLOR", (0, len(budget_data) - 1), (-1, -1), colors.white)
        t.setStyle(ts)
        story.append(t)
        story.append(Spacer(1, 0.4 * cm))

    story.append(PageBreak())

    # ── 每日行程 ──────────────────────────────────────────────────────────
    for idx, day in enumerate(plan.days):
        day_num = idx + 1
        date_str = day.date or ""
        theme = day.description or ""

        # 日期标题
        story.append(Paragraph(
            f"  Day {day_num}   {date_str}   {theme}",
            S["day_header"]
        ))
        story.append(Spacer(1, 0.2 * cm))

        # 景点表格
        if day.attractions:
            story.append(Paragraph("🏛 景点", S["section"]))
            rows = [["景点名称", "地址", "时长(分钟)", "票价(元)"]]
            for a in day.attractions:
                rows.append([
                    a.name,
                    a.address or "—",
                    str(a.visit_duration),
                    f"¥{a.ticket_price}" if a.ticket_price else "免费",
                ])
            t = Table(rows, colWidths=[5 * cm, 7 * cm, 2.5 * cm, 2.5 * cm])
            t.setStyle(_table_style())
            story.append(t)
            story.append(Spacer(1, 0.3 * cm))

        # 餐饮表格
        if day.meals:
            story.append(Paragraph("🍜 餐饮安排", S["section"]))
            rows = [["餐次", "餐厅 / 美食", "地址", "人均(元)"]]
            for m in day.meals:
                cost = getattr(m, "estimated_cost", None) or getattr(m, "price_per_person", 0)
                rows.append([
                    _meal_type_label(m.type),
                    m.name,
                    m.address or "—",
                    f"¥{cost}" if cost else "—",
                ])
            t = Table(rows, colWidths=[2.5 * cm, 5 * cm, 6 * cm, 2.5 * cm])
            t.setStyle(_table_style())
            story.append(t)
            story.append(Spacer(1, 0.3 * cm))

        # 住宿信息
        if day.hotel:
            h = day.hotel
            story.append(Paragraph("🏨 当晚住宿", S["section"]))
            hotel_text = (
                f"<b>{h.name}</b>　　📍 {h.address or '—'}"
                f"　　💰 ¥{h.estimated_cost}/晚" if h.estimated_cost else
                f"<b>{h.name}</b>　　📍 {h.address or '—'}"
            )
            story.append(Paragraph(hotel_text, S["body"]))
            story.append(Spacer(1, 0.3 * cm))

        # 天气信息（如有）
        weather = next((w for w in plan.weather_info if w.date == day.date), None)
        if weather:
            warn = f"  ⚠️ {weather.weather_warning}" if weather.weather_warning else ""
            story.append(Paragraph(
                f"🌤 天气：白天 {weather.day_weather} {weather.day_temp}℃ "
                f"/ 夜间 {weather.night_weather} {weather.night_temp}℃{warn}",
                S["hint"]
            ))

        story.append(HRFlowable(width="100%", thickness=0.5, color=COLOR_BORDER, spaceAfter=6))

        # 每天结束后如不是最后一天则换页
        if idx < len(plan.days) - 1:
            story.append(PageBreak())

    # ── 末页版权 ──────────────────────────────────────────────────────────
    story.append(Spacer(1, 1 * cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("本行程册由 HelloAgents 旅行规划平台 AI 自动生成，仅供参考。", S["footer"]))
    story.append(Paragraph("出行前请确认景点开放时间、门票预订及天气变化，祝旅途愉快！🎉", S["footer"]))

    doc.build(story)
    return buf.getvalue()
