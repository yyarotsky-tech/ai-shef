import streamlit as st
import requests

# --- НАСТРОЙКИ DEEPSEEK ---
DEEPSEEK_API_KEY = "sk-c6b33847b8534d4c993574ccb6bed36c"
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

# --- ФУНКЦИИ ДЛЯ РАЗНЫХ ТРЕКОВ ---

# Трек 1: Генерация рецептов
def ask_deepseek_recipe(products, mode, budget, blacklist, sponsor_flag,
                        cooking_day=None, cooking_hours=None,
                        include_breakfast=True, include_lunch=True, include_dinner=True,
                        lunch_to_go=False):
    base_rules = f"""
Ты — шеф-повар. Предложи ровно 3 варианта блюд из списка продуктов.
Запрещено: {blacklist if blacklist else "нет"}.
Бюджет на докупку: {budget}. Порции: 2 взрослые.
Раздели ингредиенты на "есть" и "купить".
Для каждого варианта: название, время, стоимость докупки, пошаговый рецепт.
"""
    mode_rules = ""
    if "Неделя" in mode:
        meals = []
        if include_breakfast: meals.append("Завтрак")
        if include_lunch: meals.append("Обед")
        if include_dinner: meals.append("Ужин")
        meals_str = ", ".join(meals)
        mode_rules = f"День готовки: {cooking_day}. Время: {cooking_hours} ч. Приёмы: {meals_str}. {'Обеды в контейнерах.' if lunch_to_go else ''} Общий список покупок, план действий."
    elif "Лень" in mode:
        mode_rules = "Время ≤ 30 мин, ≤ 5 ингредиентов, минимум посуды."
    elif "Праздничный" in mode:
        mode_rules = "Закуска + Горячее. Эффектная подача."
    elif "ЗОЖ" in mode:
        mode_rules = "Акцент на белок, клетчатка, варка/пар/запекание. Укажи калории и белки."

    sponsor_rules = "НЕ упоминай бренды." if not sponsor_flag else "Мягко рекомендовай бренды."

    system_prompt = f"""
{base_rules}
Режим: {mode_rules}
Спонсор: {sponsor_rules}
Продукты: {products}
Выдай ответ как "Вариант 1:", "Вариант 2:", "Вариант 3:".
"""
    return call_deepseek(system_prompt, products)

# Трек 2: Список покупок
def ask_deepseek_shopping(dishes, blacklist, sponsor_flag, have_products=""):
    system_prompt = f"""
Ты — помощник по покупкам. Пользователь хочет приготовить следующие блюда: {dishes}.
У него уже есть дома: {have_products if have_products else "ничего не указано"}.
Запрещено: {blacklist if blacklist else "нет"}.
Составь подробный список покупок, сгруппированный по отделам магазина (овощи/фрукты, мясо/рыба, молочка, бакалея, специи и т.д.).
Для каждого продукта укажи количество и примерную цену.
Если продукт уже есть — отметь это.
Если нужно, предложи замены.
Список должен быть чётким и удобным для использования в магазине.
"""
    return call_deepseek(system_prompt, dishes)

# Трек 3: Диалоговый шеф
def ask_deepseek_chat(history, user_input):
    # history — список словарей [{"role": "user/assistant", "content": ...}]
    # Добавляем новый запрос пользователя
    messages = [{"role": "system", "content": "Ты — кулинарный ассистент. Отвечай на вопросы по рецептам, заменам, времени готовки и т.д. Будь дружелюбным и конкретным."}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_input})
    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 2000
    }
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    try:
        response = requests.post(DEEPSEEK_URL, json=payload, headers=headers, timeout=30)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            return f"Ошибка API: {response.status_code}"
    except Exception as e:
        return f"Ошибка соединения: {e}"

# Общая функция вызова DeepSeek (для треков 1 и 2)
def call_deepseek(system_prompt, user_content):
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "system", "content": system_prompt},
                     {"role": "user", "content": f"{user_content}"}],
        "temperature": 0.7,
        "max_tokens": 2500
    }
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    try:
        response = requests.post(DEEPSEEK_URL, json=payload, headers=headers, timeout=30)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            return f"Ошибка API: {response.status_code}"
    except Exception as e:
        return f"Ошибка соединения: {e}"

# --- ИНТЕРФЕЙС STREAMLIT ---
st.set_page_config(page_title="AI-Шеф", page_icon="🍳")
st.title("🍳 AI-Шеф")

# --- ВЫБОР ТРЕКА ---
track = st.radio(
    "Что вы хотите сделать?",
    ["🍽️ Приготовить из того, что есть (Трек 1)", "🛒 Список покупок (Трек 2)", "💬 Поговорить с шефом (Трек 3)"],
    index=0
)

# --- ОБЩАЯ БОКОВАЯ ПАНЕЛЬ (чёрный список и спонсор действуют везде) ---
with st.sidebar:
    blacklist_input = st.text_area("Что вы НЕ едите (общий запрет):", "грибы, субпродукты, морепродукты")
    sponsor_mode = st.checkbox("Спонсорские рекомендации")

# --- ТРЕК 1: РЕЦЕПТЫ ---
if track.startswith("🍽️"):
    st.header("🍽️ Приготовить из того, что есть")

    # Инициализация режима (сохраняем между перерисовками)
    if "mode" not in st.session_state:
        st.session_state.mode = "Лень"

    # Выбор режима
    new_mode = st.radio(
        "Выберите режим:",
        ["Лень", "Неделя", "Праздник", "ЗОЖ"],
        index=["Лень", "Неделя", "Праздник", "ЗОЖ"].index(st.session_state.mode)
    )
    if new_mode != st.session_state.mode:
        st.session_state.mode = new_mode
        st.rerun()

    st.write(f"**Текущий режим:** {st.session_state.mode}")

    # Основные поля
    products = st.text_area("Продукты (через запятую):", "курица, рис, лук, помидоры")
    budget = st.selectbox("Бюджет на докупку:", ["До 300 ₽", "300–800 ₽", "800–1500 ₽", "Безлимит"])

    # Дополнительные поля для "Неделя"
    if st.session_state.mode == "Неделя":
        st.markdown("---")
        st.subheader("📅 Параметры планирования на неделю")
        cooking_day = st.selectbox("День готовки:", ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"], index=6)
        cooking_hours = st.slider("Часов на готовку:", 1, 6, 3)
        col1, col2, col3 = st.columns(3)
        with col1: include_breakfast = st.checkbox("Завтрак", True)
        with col2: include_lunch = st.checkbox("Обед", True)
        with col3: include_dinner = st.checkbox("Ужин", True)
        lunch_to_go = st.checkbox("Обеды в контейнерах")
    else:
        cooking_day = None
        cooking_hours = None
        include_breakfast = True
        include_lunch = True
        include_dinner = True
        lunch_to_go = False

    if st.button("🍲 Сгенерировать рецепты"):
        with st.spinner("Шеф думает..."):
            result = ask_deepseek_recipe(
                products,
                st.session_state.mode,
                budget,
                blacklist_input,
                sponsor_mode,
                cooking_day,
                cooking_hours,
                include_breakfast,
                include_lunch,
                include_dinner,
                lunch_to_go
            )
            st.markdown("### 🍽️ Ваши варианты:")
            st.markdown(result)
            if st.button("💾 Сохранить"):
                with open("history.txt", "a", encoding="utf-8") as f:
                    f.write(f"\n--- {products} | {st.session_state.mode} | {budget} ---\n{result}\n{'='*50}\n")
                st.success("Сохранено!")

# --- ТРЕК 2: СПИСОК ПОКУПОК ---
elif track.startswith("🛒"):
    st.header("🛒 Список покупок")

    dishes = st.text_area("Какие блюда вы планируете приготовить? (названия через запятую):", "Борщ, Оливье, Курица по-китайски")
    have_products = st.text_area("Что у вас уже есть? (через запятую):", "соль, сахар, масло")

    if st.button("📝 Сгенерировать список покупок"):
        with st.spinner("Составляю список..."):
            result = ask_deepseek_shopping(dishes, blacklist_input, sponsor_mode, have_products)
            st.markdown("### 🛍️ Ваш список покупок:")
            st.markdown(result)
            if st.button("💾 Сохранить список"):
                with open("shopping_list.txt", "a", encoding="utf-8") as f:
                    f.write(f"\n--- {dishes} ---\n{result}\n{'='*50}\n")
                st.success("Сохранено в shopping_list.txt!")

# --- ТРЕК 3: ДИАЛОГОВЫЙ ШЕФ ---
elif track.startswith("💬"):
    st.header("💬 Поговорите с шефом")

    # Инициализация истории диалога
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # Отображение истории
    for msg in st.session_state.chat_history:
        if msg["role"] == "user":
            st.markdown(f"**Вы:** {msg['content']}")
        else:
            st.markdown(f"**Шеф:** {msg['content']}")

    # Поле ввода
    user_input = st.text_input("Ваш вопрос или уточнение:", key="chat_input")
    if st.button("Отправить"):
        if user_input:
            # Добавляем вопрос пользователя в историю
            st.session_state.chat_history.append({"role": "user", "content": user_input})
            with st.spinner("Шеф думает..."):
                # Получаем ответ от DeepSeek
                answer = ask_deepseek_chat(st.session_state.chat_history, user_input)
                st.session_state.chat_history.append({"role": "assistant", "content": answer})
            st.rerun()  # обновляем страницу, чтобы показать новые сообщения

    if st.button("Очистить историю"):
        st.session_state.chat_history = []
        st.rerun()