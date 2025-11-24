import streamlit as st
import pandas as pd
import re
import matplotlib.pyplot as plt

st.set_page_config(page_title="Универсальный анализ СОР/СОЧ", layout="wide")
st.title("Умный анализ СОР/СОЧ (стабильная версия без ошибок)")

files = st.file_uploader(
    "Загрузите любые файлы СОР/СОЧ (xls, xlsx, csv)",
    type=["xlsx", "xls", "csv"],
    accept_multiple_files=True
)

# ---------- РАСПОЗНАВАНИЕ КОЛОНОК ----------
def guess_column(columns, keywords):
    """Пытается угадать имя столбца по ключевым словам"""
    for col in columns:
        for k in keywords:
            if k.lower() in col.lower():
                return col
    return None


def extract_numeric(value):
    """Извлекает оценку 1–5 из любых строк"""
    if pd.isna(value):
        return None
    match = re.search(r"[1-5]", str(value))
    return int(match.group()) if match else None


# ---------------------------------------------------

if files:
    merged = pd.DataFrame()
    skipped_files = []

    for file in files:

        # ---- загрузка файла ----
        try:
            if file.name.endswith(".csv"):
                df = pd.read_csv(file)
            else:
                df = pd.read_excel(file)
        except Exception as e:
            skipped_files.append((file.name, f"Ошибка чтения файла: {e}"))
            continue

        # -------- попытка угадать нужные колонки --------
        col_name = guess_column(df.columns, ["ФИО", "Имя", "Аты", "Оқушы"])
        col_class = guess_column(df.columns, ["Класс", "Сынып", "Топ", "Class"])
        col_mark = guess_column(df.columns, ["Оцен", "Бағ", "Бал", "Mark", "Итог"])

        # если оценка не найдена — ищем любой столбец с цифрами 2–5
        if col_mark is None:
            for c in df.columns:
                if df[c].astype(str).str.contains(r"[2-5]").sum() > 0:
                    col_mark = c
                    break

        # если нет класса или нет оценок → пропускаем файл
        if col_class is None or col_mark is None:
            skipped_files.append(
                (file.name,
                 f"Не удалось найти нужные столбцы. class={col_class}, mark={col_mark}")
            )
            continue

        # ---- создаем таблицу ----
        tmp = pd.DataFrame()
        tmp["class"] = df[col_class]
        tmp["mark"] = df[col_mark].apply(extract_numeric)

        tmp["name"] = df[col_name] if col_name else None

        merged = pd.concat([merged, tmp], ignore_index=True)

    # --- если нечего анализировать ---
    if merged.empty:
        st.error("Не удалось обработать ни один файл. Проверьте структуру данных.")
        if skipped_files:
            st.warning("Пропущенные файлы:")
            for name, reason in skipped_files:
                st.write(f"❌ {name} — {reason}")
        st.stop()

    # Показать пропущенные файлы
    if skipped_files:
        st.warning("Некоторые файлы пропущены:")
        for name, reason in skipped_files:
            st.write(f"❌ **{name}** — {reason}")

    st.subheader("Распознанные данные")
    st.dataframe(merged)

    merged = merged.dropna(subset=["mark"])

    # ---------- АНАЛИТИКА ----------
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

    # ---------- ГРАФИК ----------
    st.subheader("📈 Диаграмма качества и успеваемости")
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(result["class"], result["quality %"], marker="o", label="Качество %")
    ax.plot(result["class"], result["success %"], marker="o", label="Успеваемость %")
    ax.legend()
    ax.grid(True)
    st.pyplot(fig)

    # ---------- ВЫВОДЫ И РЕКОМЕНДАЦИИ ----------
    st.subheader("📌 Автоматические выводы и рекомендации")

    text = ""
    for _, row in result.iterrows():
        cls = row["class"]
        q = row["quality %"]
        s = row["success %"]
        tw = row["twos"]

        text += f"### Класс {cls}\n"
        text += f"- Качество: **{q}%**, успеваемость: **{s}%**\n"

        if q < 50:
            text += "- Низкое качество: требуется повторение ключевых тем.\n"
        if tw > 0:
            text += f"- Имеется {tw} двоек — нужна коррекционная работа.\n"
        if q > 75:
            text += "- Отличный уровень качества.\n"
        text += "\n"

    st.markdown(text)

    st.success("Готово! Анализ успешно выполнен.")


