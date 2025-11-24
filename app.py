# app.py — финальная версия
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import re
import os

st.set_page_config(page_title="AI Анализ СОР/СОЧ", layout="wide")
st.title("📊 AI-Анализатор СОР/СОЧ — устойчивый парсер + PDF")

st.write("Загрузите Excel-файл из Кунделика. Приложение автоматически найдёт СОР/СОЧ, построит цветные диаграммы и сформирует корректный PDF с кириллицей.")

uploaded = st.file_uploader("Загрузите файл Excel из Кунделика", type=["xlsx"]) 

# Попытка зарегистрировать системный DejaVu-шрифт для корректной кириллицы в PDF
DEJAVU_PATH = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
if not os.path.exists(DEJAVU_PATH):
    # если хотите, загрузите DejaVuSans.ttf в репозиторий и укажите относительный путь, например './DejaVuSans.ttf'
    DEJAVU_PATH = './DejaVuSans.ttf'  # fallback: пользователь может положить файл рядом с app.py
if os.path.exists(DEJAVU_PATH):
    try:
        pdfmetrics.registerFont(TTFont('DejaVu', DEJAVU_PATH))
    except Exception:
        pass

def find_header_indices(df_raw):
    """Ищем строки, содержащие подсказки заголовков: 'низкий', 'Количество учеников', '% качества' и т.д."""
    header_rows = []
    for i, row in df_raw.iterrows():
        row_text = ' '.join([str(x) for x in row.astype(str).values if x is not None])
        if re.search(r'низк|низкий|процент|% качества|% успеваемости|количество учеников', row_text, flags=re.I):
            header_rows.append(i)
    return header_rows

def locate_percentage_columns(df_raw, header_rows):
    """Попытаемся найти индексы столбцов для '% качества' и '% успеваемости' по содержимому заголовочных строк."""
    pct_col = None
    pass_col = None
    for r in header_rows:
        row = df_raw.iloc[r].astype(str)
        for idx, val in row.items():
            v = str(val).lower()
            if 'качест' in v or '% качества' in v or 'качество' in v:
                pct_col = idx
            if 'успеваем' in v or '% успеваемости' in v or 'успеваемост' in v:
                pass_col = idx
    return pct_col, pass_col

def robust_extract_sor_rows(df_raw):
    """Ищем строки, где в первой колонке встречается 'СОР' или 'СОЧ' (любые регистры/пробелы).
    Возвращаем DataFrame с найденными строками."""
    pattern = re.compile(r'\bс\s*о\s*р\b|\bсор\b|\bсоч\b|\bфоч\b', flags=re.I)
    matches = []
    for i, row in df_raw.iterrows():
        # check first column
        first = ''
        try:
            first = str(row.iloc[0])
        except Exception:
            first = ''
        if first and pattern.search(first):
            matches.append((i, row))
    if not matches:
        # альтернативно ищем по вхождению 'СОР' в любой ячейке строки
        for i, row in df_raw.iterrows():
            row_text = ' '.join([str(x) for x in row.astype(str).values if x is not None])
            if pattern.search(row_text):
                matches.append((i, row))
    if not matches:
        return pd.DataFrame()
    rows = [r for _, r in matches]
    df = pd.DataFrame(rows)
    df = df.reset_index(drop=True)
    return df

def infer_columns_by_numeric_pattern(df_rows):
    """Если заголовки не помогли — попробуем угадать колонки по числам (0-100 для процентов)."""
    pct_idx = None
    pass_idx = None
    for col in df_rows.columns:
        series = pd.to_numeric(df_rows[col], errors='coerce')
        if series.notna().any():
            vals = series.dropna()
            if ((vals >= 0) & (vals <= 100)).all():
                if pct_idx is None:
                    pct_idx = col
                elif pass_idx is None and col != pct_idx:
                    pass_idx = col
    return pct_idx, pass_idx

if uploaded:
    df_raw = pd.read_excel(uploaded, header=None, engine='openpyxl')

    st.subheader('📄 Исходная таблица (показаны первые 40 строк)')
    st.dataframe(df_raw.head(40))

    header_rows = find_header_indices(df_raw)
    pct_col, pass_col = locate_percentage_columns(df_raw, header_rows)
    df_sor = robust_extract_sor_rows(df_raw)

    if df_sor.empty:
        st.error('Не удалось найти строки СОР/СОЧ в таблице. Проверьте файл. (Парсер искал слова СОР/СОЧ в таблице)')
    else:
        # если не нашли столбцы через заголовок — попытаемся угадать по числам
        if pct_col is None or pass_col is None:
            guessed_pct, guessed_pass = infer_columns_by_numeric_pattern(df_sor)
            if pct_col is None:
                pct_col = guessed_pct
            if pass_col is None:
                pass_col = guessed_pass

        res = pd.DataFrame()
        res['Работа'] = df_sor.iloc[:,0].astype(str)

        if pct_col is not None and pct_col in df_sor.columns:
            res['% качества'] = pd.to_numeric(df_sor[pct_col], errors='coerce').fillna(0)
        else:
            res['% качества'] = 0
        if pass_col is not None and pass_col in df_sor.columns:
            res['% успеваемости'] = pd.to_numeric(df_sor[pass_col], errors='coerce').fillna(0)
        else:
            res['% успеваемости'] = 0

        # Попытка взять 'Выполнили' и 'Не выполнили' — смотрим слева от pct_col
        if pct_col is not None:
            left_cols = [c for c in df_sor.columns if c < pct_col]
            nums = []
            for c in reversed(left_cols):
                series = pd.to_numeric(df_sor[c], errors='coerce')
                if series.notna().any():
                    nums.append(c)
                if len(nums) >= 2:
                    break
            if len(nums) >= 2:
                res['Выполнили'] = pd.to_numeric(df_sor[nums[1]], errors='coerce').fillna(0).astype(int)
                res['Не выполнили'] = pd.to_numeric(df_sor[nums[0]], errors='coerce').fillna(0).astype(int)
            else:
                possible = []
                for c in df_sor.columns:
                    s = pd.to_numeric(df_sor[c], errors='coerce')
                    if s.notna().any():
                        if s.dropna().between(0,200).all():
                            possible.append(c)
                if len(possible) >= 2:
                    res['Выполнили'] = pd.to_numeric(df_sor[possible[0]], errors='coerce').fillna(0).astype(int)
                    res['Не выполнили'] = pd.to_numeric(df_sor[possible[1]], errors='coerce').fillna(0).astype(int)
                else:
                    res['Выполнили'] = 0
                    res['Не выполнили'] = 0
        else:
            res['Выполнили'] = 0
            res['Не выполнили'] = 0

        res['% качества'] = res['% качества'].astype(float).round(1)
        res['% успеваемости'] = res['% успеваемости'].astype(float).round(1)

        st.subheader('✅ Обработанные результаты')
        st.dataframe(res)

        st.markdown('<br>', unsafe_allow_html=True)

        # --- Цветные диаграммы ---
        def color_quality(x):
            if x >= 85:
                return '#2ca02c'
            elif x >= 70:
                return '#ffcc00'
            else:
                return '#d62728'

        def color_pass(x):
            if x >= 90:
                return '#2ca02c'
            elif x >= 70:
                return '#ff9900'
            else:
                return '#d62728'

        st.subheader('📈 Процент качества (цветная)')
        colors_q = [color_quality(x) for x in res['% качества']]
        fig_q, ax_q = plt.subplots(figsize=(8,4))
        bars = ax_q.bar(res['Работа'], res['% качества'], color=colors_q)
        ax_q.set_ylim(0, 100)
        ax_q.set_ylabel('% качества')
        ax_q.set_xticklabels(res['Работа'], rotation=25, ha='right')
        for bar, val in zip(bars, res['% качества']):
            ax_q.text(bar.get_x()+bar.get_width()/2, val+1, f"{val:.0f}%", ha='center', fontsize=9)
        plt.tight_layout()
        st.pyplot(fig_q)

        st.markdown('<br>', unsafe_allow_html=True)
        st.subheader('📈 Процент успеваемости (цветная)')
        colors_p = [color_pass(x) for x in res['% успеваемости']]
        fig_p, ax_p = plt.subplots(figsize=(8,4))
        bars2 = ax_p.bar(res['Работа'], res['% успеваемости'], color=colors_p)
        ax_p.set_ylim(0, 100)
        ax_p.set_ylabel('% успеваемости')
        ax_p.set_xticklabels(res['Работа'], rotation=25, ha='right')
        for bar, val in zip(bars2, res['% успеваемости']):
            ax_p.text(bar.get_x()+bar.get_width()/2, val+1, f"{val:.0f}%", ha='center', fontsize=9)
        plt.tight_layout()
        st.pyplot(fig_p)

        # --- Анализ в тексте ---
        st.subheader('🔍 AI-диагностика проблемных тем')
        analysis = []
        for _, row in res.iterrows():
            work = row['Работа']
            q = row['% качества']
            if q < 70:
                analysis.append(f"❗ {work}: низкое качество ({q}%). Рекомендуется диагностика и повторение.")
            elif q < 85:
                analysis.append(f"⚠️ {work}: средние результаты ({q}%). Стоит уделить внимание сложным заданиям.")
            else:
                analysis.append(f"✅ {work}: высокий уровень ({q}%).")
        st.write('\\n'.join(analysis))

        # --- Попытка извлечь список учеников по уровням (если есть) ---
        students_by_level = {}
        for i, row in df_raw.iterrows():
            row_text = ' '.join([str(x) for x in row.astype(str).values if x is not None])
            if re.search(r'низк|высок|средн', row_text, flags=re.I):
                for col_idx, val in df_raw.iloc[i].items():
                    if isinstance(val, str) and ('низк' in val.lower() or 'сред' in val.lower() or 'высок' in val.lower()):
                        key = val.strip()
                        names = []
                        for c in range(col_idx+1, col_idx+6):
                            if c in df_raw.columns:
                                v = df_raw.iat[i, c]
                                if v and str(v).strip() not in ['nan','None','']:
                                    names.append(str(v))
                        students_by_level[key] = ', '.join(names)
        if students_by_level:
            st.subheader('👥 Ученики по уровням (если найдены)')
            for k,v in students_by_level.items():
                st.write(f"**{k}**: {v}")

        # --- PDF генерация (с кириллицей, диаграммами) ---
        st.subheader('📥 Скачать PDF-отчёт')

        def create_pdf_bytes(res_table, fig_quality, fig_pass, analysis_lines, students_dict):
            buffer = BytesIO()
            p = canvas.Canvas(buffer, pagesize=A4)
            width, height = A4
            font_name = 'DejaVu' if 'DejaVu' in pdfmetrics.getRegisteredFontNames() else 'Helvetica'
            p.setFont(font_name, 14)
            p.drawString(40, height-40, 'Анализ результатов СОР и СОЧ')

            # таблица
            p.setFont(font_name, 10)
            y = height - 70
            col_x = [40, 210, 280, 360, 460]
            headers = ['Работа', 'Выполнили', 'Не выполнили', '% качества', '% успеваемости']
            for i,h in enumerate(headers):
                p.drawString(col_x[i], y, h)
            y -= 18
            for _, r in res_table.iterrows():
                if y < 120:
                    p.showPage()
                    p.setFont(font_name, 10)
                    y = height - 40
                p.drawString(col_x[0], y, str(r['Работа']))
                p.drawString(col_x[1], y, str(int(r['Выполнили'])))
                p.drawString(col_x[2], y, str(int(r['Не выполнили'])))
                p.drawString(col_x[3], y, f"{r['% качества']:.0f}%")
                p.drawString(col_x[4], y, f"{r['% успеваемости']:.0f}%")
                y -= 15

            # графики (сохраняем в буферы и вставляем)
            img_buf1 = BytesIO()
            fig_quality.savefig(img_buf1, format='png', bbox_inches='tight')
            img_buf1.seek(0)
            img1 = ImageReader(img_buf1)

            img_buf2 = BytesIO()
            fig_pass.savefig(img_buf2, format='png', bbox_inches='tight')
            img_buf2.seek(0)
            img2 = ImageReader(img_buf2)

            p.showPage()
            try:
                p.drawImage(img1, 40, height/2 + 20, width=520, preserveAspectRatio=True, mask='auto')
                p.drawImage(img2, 40, 40, width=520, preserveAspectRatio=True, mask='auto')
            except Exception:
                pass

            # AI-анализ
            p.showPage()
            p.setFont(font_name, 12)
            p.drawString(40, height-40, 'AI-диагностика')
            p.setFont(font_name, 10)
            y = height - 70
            for line in analysis_lines:
                if y < 40:
                    p.showPage()
                    p.setFont(font_name, 10)
                    y = height - 40
                p.drawString(40, y, line[:120])
                y -= 14

            # ученики по уровням
            if students_dict:
                p.showPage()
                p.setFont(font_name, 12)
                p.drawString(40, height-40, 'Ученики по уровням')
                p.setFont(font_name, 10)
                y = height - 70
                for k,v in students_dict.items():
                    if y < 40:
                        p.showPage()
                        y = height - 40
                    p.drawString(40, y, f"{k}: {v[:200]}")
                    y -= 14

            p.save()
            buffer.seek(0)
            return buffer.getvalue()

        if st.button('Сформировать PDF'):
            pdf_bytes = create_pdf_bytes(res, fig_q, fig_p, analysis, students_by_level)
            st.download_button('Скачать PDF', data=pdf_bytes, file_name='report_SOR_SOCH.pdf', mime='application/pdf')

        st.info('Готово — попробуйте нажать \"Сформировать PDF\". Если в PDF кириллица не отображается, загрузите DejaVuSans.ttf рядом с app.py или укажите другой TTF-шрифт.')
