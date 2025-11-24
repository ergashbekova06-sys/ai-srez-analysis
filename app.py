import streamlit as st
import pandas as pd
import re
import matplotlib.pyplot as plt

st.set_page_config(page_title="Умный анализ СОР/СОЧ", layout="wide")
st.title("Универсальная программа анализа СОР/СОЧ")

st.write("Загрузите любые файлы — программа сама поймёт формат и извлечёт оценки.")

files = st.file_uploader(
    "Загрузите файлы (Excel / CSV / даже разные форматы)",
    type=["xlsx", "xls", "csv"],
    accept_multiple_files=True
)

# ---------- ФУНКЦИИ РАСПОЗНАВАНИЯ ----------------

def guess_column(columns, keywords):
    """Пытается угадать имя столбца по ключевым словам"""
    for col in columns:
        for k in keywords:
            if k.lower() in col.lower():
                return col
    return None

def extract_numeric(value):
    """Извлекает числовую оценку из любой строки"""
    if pd.isna(value):
        return None
    match = re.search(r"[1-5]", str(value))
    return int(match.group()) if match else None


# ---------------------------------------------------

if files:
    merged = pd.DataFrame()

    for file in files:
        if file.name.endswith(".csv"):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)

        original = df.copy()

        # Попытка найти столбцы с ФИО, классом, оценками
        col_name = guess_column(df.columns, ["ФИО", "Оқушы", "Имя", "Аты"])
        col_class = guess_column(df.columns, ["Класс", "Сынып", "Топ"])
        col_mark = guess_column(df.columns, ["Оцен", "Баға", "Бал", "Mark"])

        # Если не нашли — пробуем угадать по типам данных
        if col_mark is None:
            # ищем столбец, где встречаются цифры 2-5
            for c in df.columns:
                sample = df[c].astype(str).str.contains(r"[2-5]").sum()
                if sample > 0:
                    col_mark = c
                    break

        df = df[[col_name, col_class, col_mark]].copy()

        df.columns = ["name", "class", "mark"]
        df["mark"] = df["mark"].apply(extract_numeric)

        merged = pd.concat([merged, df], ignore_index=True)

    st.subheader("Распознанные данные")
    st.dataframe(merged)

    merged = merged.dropna(subset=["mark"])  # убираем строки без оценок

    # --- ГРУППИРОВКА ---
    result = (
        merged.groupby("class")["mark"]
        .agg(
            total="count",
            fives=lambda x: (x == 5).sum(),
            fours=lambda x: (x == 4).sum(),
            threes=lambda x: (x == 3).sum(),
            twos=lambda x: (x == 2).sum(),
        )
        .reset_index()
    )

    result["quality %"] = ((result["fives"] + result["fours"]) / result["total"] * 100).round(1)
    result["success %"] = ((result["total"] - result["twos"]) / result["total"] * 100).round(1)

    st.subheader("📊 Итоговая таблица")
    st.dataframe(result)

    # --- ДИАГРАММА ---
    st.subheader("📈 Диаграмма качества и успеваемости")
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(result["class"], result["quality %"], marker="o", label="Качество %")
    ax.plot(result["class"], result["success %"], marker="o", label="Успеваемость %")
    ax.legend()
    ax.grid(True)
    st.pyplot(fig)

    # --- ВЫВОДЫ ---
    st.subheader("📌 Автоматические выводы и рекомендации")

    text = ""
    for _, row in result.iterrows():
        cls = row["class"]
        q = row["quality %"]
        s = row["success %"]
        two = row["twos"]

        text += f"### Класс {cls}\n"
        text += f"- Качество: **{q}%**, успеваемость: **{s}%**\n"

        if q < 50:
            text += "- Низкий уровень качества: необходимо повторение ключевых тем.\n"
        if two > 0:
            text += f"- Есть {two} учащихся с оценкой '2'. Нужна корректирующая работа.\n"
        if q > 75:
            text += "- Высокое качество — обучение идёт эффективно.\n"
        text += "\n"

    st.markdown(text)

    st.success("Готово! Программа автоматически проанализировала файлы.")


