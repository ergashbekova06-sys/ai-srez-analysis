# Streamlit AI Analyzer — продвинутая версия с PDF-экспортом и цветными диаграммами

import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader

st.set_page_config(page_title="AI Анализ СОР/СОЧ", layout="wide")
st.title("📊 AI-Анализатор СОР/СОЧ и Тем Ошибок")

st.write("Загрузите Excel-файл из Кунделика. Приложение автоматически найдет строки СОР/СОЧ, построит цветные диаграммы и сформирует PDF-отчёт.")

uploaded = st.file_uploader("Загрузите файл Excel из Кунделика", type=["xlsx"])

if uploaded:
    df_raw = pd.read_excel(uploaded, header=None)

    # --- 1. Поиск строк СОР/СОЧ ---
    mask = df_raw[0].astype(str).str.contains("СОР|СОЧ", case=False, na=False)
    df = df_raw[mask].copy()
    df = df.reset_index(drop=True)

    # Защита: если формат отличается — подберём минимальные индексы безопасно
    # Берём колонки 0,1,2,7,8 если существуют, иначе берём доступные
    cols_available = list(df.columns)
    desired = []
    for c in [0,1,2,7,8]:
        if c in cols_available:
            desired.append(c)
        else:
            desired.append(cols_available[min(len(cols_available)-1, c)])

    df = df[desired]
    df.columns = ["Работа","Выполнили","Не выполнили","% качества","% успеваемости"]

    # Приведём числовые колонки к числам
    for col in ["Выполнили","Не выполнили","% качества","% успеваемости"]:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    st.subheader("📄 Обработанные данные")
    st.dataframe(df)

    # --- 2. Цветная диаграмма качества ---
    st.subheader("📈 Процент качества (цветная)")
    def color_quality(x):
        if x >= 85:
            return '#2ca02c'  # зелёный
        elif x >= 70:
            return '#ffcc00'  # жёлтый
        else:
            return '#d62728'  # красный

    colors_q = [color_quality(x) for x in df['% качества']]
    fig_q, ax_q = plt.subplots(figsize=(6,4))
    bars = ax_q.bar(df['Работа'], df['% качества'], color=colors_q)
    ax_q.set_ylabel('% качества')
    ax_q.set_ylim(0,100)
    for bar, val in zip(bars, df['% качества']):
        ax_q.text(bar.get_x()+bar.get_width()/2, val+1, f"{val:.0f}%", ha='center')
    st.pyplot(fig_q)

    # --- 3. Цветная диаграмма успеваемости ---
    st.subheader("📈 Процент успеваемости (цветная)")
    def color_pass(x):
        if x >= 90:
            return '#2ca02c'  # зелёный
        elif x >= 70:
            return '#ff9900'  # оранжевый
        else:
            return '#d62728'  # красный

    colors_p = [color_pass(x) for x in df['% успеваемости']]
    fig_p, ax_p = plt.subplots(figsize=(6,4))
    bars2 = ax_p.bar(df['Работа'], df['% успеваемости'], color=colors_p)
    ax_p.set_ylabel('% успеваемости')
    ax_p.set_ylim(0,100)
    for bar, val in zip(bars2, df['% успеваемости']):
        ax_p.text(bar.get_x()+bar.get_width()/2, val+1, f"{val:.0f}%", ha='center')
    st.pyplot(fig_p)

    # --- 4. Продвинутый анализ ошибок (текст) ---
    st.subheader("🔍 AI-диагностика проблемных тем")
    analysis = []
    for _, row in df.iterrows():
        work = str(row['Работа'])
        q = float(row['% качества'])
        if q < 70:
            analysis.append(f"❗ {work}: низкое качество ({q:.0f}%). Требуется повторение и дополнительная диагностика.")
        elif q < 85:
            analysis.append(f"⚠️ {work}: средние результаты ({q:.0f}%). Рекомендуется дополнительная работа по трудным заданиям.")
        else:
            analysis.append(f"✅ {work}: высокий уровень ({q:.0f}%).")

    st.write("
".join(analysis))

    # --- 5. Попытка извлечь перечень учащихся по уровням (если в файле есть) ---
    students_by_level = {}
    # Ищем строку, где встречается слово 'Низкий' — и берём имена из той же строки в соседних колонках
    header_idx = None
    for i, row in df_raw.iterrows():
        row_text = ' '.join([str(x) for x in row.astype(str).values])
        if 'Низкий' in row_text or 'Средний' in row_text or 'Высокий' in row_text:
            header_idx = i
            header_row = row
            break
    if header_idx is not None:
        # берём значения в этой строке
        for col_idx, val in header_row.items():
            if isinstance(val, str) and ('Низкий' in val or 'Средний' in val or 'Высокий' in val):
                key = val.strip()
                # берем соседние ячейки правее как строку с фамилиями
                names = []
                try:
                    # объединяем следующие 3 ячеек в строку (если есть)
                    cells = []
                    for c in range(col_idx+1, col_idx+4):
                        if c in header_row.index:
                            cells.append(str(header_row[c]))
                    names_text = ', '.join([x for x in cells if x and x!='nan' and x!='None' and x.strip()!=''])
                    students_by_level[key] = names_text
                except Exception:
                    students_by_level[key] = ''

    if students_by_level:
        st.subheader('👥 Ученики по уровням (если найдены в файле)')
        for k,v in students_by_level.items():
            st.write(f"**{k}**: {v}")

    # --- 6. Генерация PDF-отчёта ---
    st.subheader('📥 Скачать PDF-отчёт')

    def create_pdf(df_table, fig_quality, fig_pass, analysis_lines, students_dict):
        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        # Заголовок
        p.setFont('Helvetica-Bold', 14)
        p.drawString(40, height-40, 'Анализ результатов СОР и СОЧ')

        # Добавим базовую таблицу результатов
        p.setFont('Helvetica', 10)
        y = height - 70
        p.drawString(40, y, 'Работа')
        p.drawString(200, y, 'Выполнили')
        p.drawString(280, y, 'Не выполнили')
        p.drawString(360, y, '% качества')
        p.drawString(460, y, '% успеваемости')
        y -= 15
        for _, r in df_table.iterrows():
            p.drawString(40, y, str(r['Работа']))
            p.drawString(200, y, str(int(r['Выполнили'])))
            p.drawString(280, y, str(int(r['Не выполнили'])))
            p.drawString(360, y, f"{int(r['% качества'])}%")
            p.drawString(460, y, f"{int(r['% успеваемости'])}%")
            y -= 15
            if y < 150:
                p.showPage()
                y = height - 40

        # Вставляем графики: сохраняем в картинки и вставляем
        img_buf1 = BytesIO()
        fig_quality.savefig(img_buf1, format='png', bbox_inches='tight')
        img_buf1.seek(0)
        img1 = ImageReader(img_buf1)

        img_buf2 = BytesIO()
        fig_pass.savefig(img_buf2, format='png', bbox_inches='tight')
        img_buf2.seek(0)
        img2 = ImageReader(img_buf2)

        # Новая страница для графиков
        p.showPage()
        p.drawImage(img1, 40, height/2, width=500, preserveAspectRatio=True, mask='auto')
        p.drawImage(img2, 40, 40, width=500, preserveAspectRatio=True, mask='auto')

        # Новая страница для анализа
        p.showPage()
        p.setFont('Helvetica-Bold', 12)
        p.drawString(40, height-40, 'AI-диагностика')
        p.setFont('Helvetica', 10)
        y = height - 70
        for line in analysis_lines:
            p.drawString(40, y, line)
            y -= 15
            if y < 40:
                p.showPage()
                y = height - 40

        # Страница учеников по уровням
        if students_dict:
            p.showPage()
            p.setFont('Helvetica-Bold', 12)
            p.drawString(40, height-40, 'Ученики по уровням')
            p.setFont('Helvetica', 10)
            y = height - 70
            for k,v in students_dict.items():
                p.drawString(40, y, f"{k}: {v}")
                y -= 15
                if y < 40:
                    p.showPage()
                    y = height - 40

        p.save()
        buffer.seek(0)
        return buffer.getvalue()

    if st.button('Сформировать и скачать PDF-отчёт'):
        pdf_bytes = create_pdf(df, fig_q, fig_p, analysis, students_by_level)
        st.download_button('Скачать PDF', data=pdf_bytes, file_name='report_SOR_SOCH.pdf', mime='application/pdf')

    st.info("Готово! PDF формируется кнопкой выше. После публикации на Streamlit Cloud приложение можно вставить на сайт через iframe.")
