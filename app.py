import streamlit as st
import requests
import json
import os
import re
from datetime import datetime

# ==============================================
#  НАСТРОЙКИ (RouterAI)
# ==============================================
try:
    ROUTERAI_API_KEY = st.secrets["ROUTERAI_API_KEY"]
except Exception:
    ROUTERAI_API_KEY = "sk-0LSxndLkCPSamb9xc4PXk8feuTp8vNyd"

ROUTERAI_URL = "https://routerai.ru/api/v1/chat/completions"
HISTORY_FILE = "user_history.json"

# ==============================================
#  РАБОТА С ИСТОРИЕЙ
# ==============================================
def get_user_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("sessions", [])

def save_user_history(query, chosen_recipe, full_recipe, situation_type, rating=None):
    history = get_user_history()
    for session in history:
        if session.get("chosen_recipe") == chosen_recipe:
            return
    
    if not os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump({"sessions": []}, f, ensure_ascii=False, indent=2)

    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    new_session = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "query": query,
        "chosen_recipe": chosen_recipe,
        "full_recipe": full_recipe,
        "situation_type": situation_type,
        "rating": rating
    }
    data["sessions"].append(new_session)

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user_profile():
    sessions = get_user_history()
    chosen = [s.get("chosen_recipe") for s in sessions if s.get("chosen_recipe")]
    situations = [s.get("situation_type") for s in sessions if s.get("situation_type")]
    return {"chosen_recipes": chosen, "situation_types": situations}

# ==============================================
#  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==============================================
def extract_recipe_name(text):
    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if line.startswith("**") and "Вариант" not in line:
            return line.replace("**", "").strip()
        if "Что приготовить:" in line:
            name = line.split("Что приготовить:")[1].strip()
            if "**" in name:
                name = name.split("**")[0].strip()
            return name
    for line in lines:
        line = line.strip()
        if line and not line.startswith(("#", "*", "-", "**", "Вариант")):
            return line[:60]
    return "Рецепт без названия"

# ==============================================
#  ФУНКЦИЯ ВЫЗОВА ROUTERAI
# ==============================================
def call_routerai(system_prompt, user_content):
    payload = {
        "model": "deepseek/deepseek-v4-flash",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "temperature": 0.7,
        "max_tokens": 3500
    }
    headers = {
        "Authorization": f"Bearer {ROUTERAI_API_KEY}",
        "Content-Type": "application/json"
    }
    try:
        response = requests.post(ROUTERAI_URL, json=payload, headers=headers, timeout=60)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            return f"Ошибка API: {response.status_code} - {response.text}"
    except Exception as e:
        return f"Ошибка соединения: {e}"

# ==============================================
#  ГЕНЕРАЦИЯ СЦЕНАРИЯ
# ==============================================
def generate_scenario(query, variant_index=0, rejected_variants=None, previous_variants=None):
    profile = get_user_profile()
    chosen_recipes = profile.get("chosen_recipes", [])
    situation_types = profile.get("situation_types", [])

    previous_context = ""
    if previous_variants:
        previous_context = f"\nРанее я уже предлагал варианты: {', '.join(previous_variants)}.\nПредложи что-то другое, не повторяй их."

    is_week_plan = any(keyword in query.lower() for keyword in ["план на неделю", "меню на неделю", "неделя"])

    if is_week_plan:
        system_prompt = f"""
Ты — помощник по планированию питания. Пользователь хочет составить план питания на неделю.

Контекст:
- Он уже выбирал рецепты: {', '.join(chosen_recipes) if chosen_recipes else 'нет данных'}
- Его типичные ситуации: {', '.join(situation_types) if situation_types else 'нет данных'}

Запрос пользователя: {query}

Твоя задача — составить чёткий план на неделю.

Алгоритм:
1. Определи, сколько человек будет питаться по плану (если не указано — 1–2 человека).
2. Определи бюджет (если не указано — 2000–3000 ₽ на неделю).
3. Составь меню на 7 дней:
   - Завтрак, обед, ужин для каждого дня.
   - Учитывай, что блюда не должны повторяться чаще 2 раз в неделю.
4. Добавь общий список покупок на неделю, сгруппированный по категориям (овощи, мясо, бакалея, молочка).
5. Добавь инструкции по приготовлению:
   - Что можно приготовить заранее (в выходной).
   - Что лучше готовить в день.
   - Сколько времени займёт приготовление каждого блюда.
6. Структура ответа:
   - **Меню на неделю** (по дням, с приёмами пищи).
   - **Список покупок** (сгруппированный).
   - **Инструкции** (что заранее, что в день).

Тон: заботливый, дружелюбный, без давления.
"""
    else:
        is_complex = any(keyword in query.lower() for keyword in ["и", "плюс", "с", "а также"]) and len(query.split()) > 10
        
        if is_complex:
            system_prompt = f"""
Ты — помощник по кулинарии и планированию меню. Пользователь описал сложный запрос, в котором перечислены несколько блюд.

Контекст:
- Он уже выбирал рецепты: {', '.join(chosen_recipes) if chosen_recipes else 'нет данных'}
- Его типичные ситуации: {', '.join(situation_types) if situation_types else 'нет данных'}

Запрос пользователя: {query}

Твоя задача — НЕ предлагать одно новое блюдо, а:
1. Определи, какие блюда перечислены в запросе.
2. Для КАЖДОГО из перечисленных блюд дай КРАТКИЙ рецепт: название, список продуктов, время приготовления, ключевые шаги.
3. Добавь общий таймлайн: что приготовить заранее, что в день, в каком порядке.
4. Предложи 1–2 связующих элемента (соус, гарнир, десерт), если их не хватает для целостности меню.
5. Дай советы по подаче: как красиво оформить, что к чему подать.
6. Если в запросе есть "что добавить" или "чего не хватает" — ответь на этот вопрос конкретно.

Структура ответа:
- **Общий план меню** (кратко).
- **Рецепты** (для каждого блюда — кратко, с ингредиентами и шагами).
- **Таймлайн** (что и когда готовить).
- **Связующие элементы** (соусы, гарниры, десерты).
- **Советы по подаче**.

Тон: заботливый, дружелюбный, без давления. Не задавай лишних вопросов — используй информацию из запроса.
"""
        else:
            system_prompt = f"""
Ты — помощник по кулинарии. Пользователь описывает свою ситуацию.

Контекст:
- Он уже выбирал рецепты: {', '.join(chosen_recipes) if chosen_recipes else 'нет данных'}
- Его типичные ситуации: {', '.join(situation_types) if situation_types else 'нет данных'}

Если он уже отклонял какие-то варианты в этом диалоге, не предлагай их снова.
{previous_context}

Ситуация пользователя: {query}

Твоя задача — дать один чёткий практичный вариант.

Алгоритм:
1. Определи ключевые параметры: время, бюджет, количество человек, состояние (устал, хочет впечатлить, планирует заранее), ограничения.
2. Если параметры не указаны, используй разумные значения по умолчанию.
3. Предложи ОДИН конкретный сценарий. Не давай альтернатив — только один вариант.
4. Учти контекст: если пользователь уже выбирал похожие блюда, предложи что-то новое или знакомое в зависимости от ситуации.
5. Структура ответа:
   - **Что приготовить** — название блюда.
   - **Список продуктов** — что нужно купить (с пометкой «купить» или «есть дома», если уместно).
   - **Пошаговая инструкция** — минимум шагов, без терминов.
   - **Совет** — 1–2 строки, как улучшить.

Тон: заботливый, дружелюбный, без давления. Не задавай лишних вопросов.
"""

    user_content = f"Запрос: {query}. Предложи вариант номер {variant_index + 1}"
    if rejected_variants:
        user_content += f". Не предлагай: {', '.join(rejected_variants)}"

    return call_routerai(system_prompt, user_content)

# ==============================================
#  ФУНКЦИЯ ДЛЯ ГЕНЕРАЦИИ СПИСКА ПОКУПОК
# ==============================================
def generate_shopping_list(menu_text, people_count=6):
    """Отправляет меню в RouterAI и получает чистый список покупок"""
    system_prompt = f"""
Ты — помощник по кулинарии. Твоя задача — составить список покупок для приготовления меню.

Меню:
{menu_text}

Требования:
1. Составь единый список продуктов для приготовления всех блюд из меню.
2. Рассчитай количество продуктов на {people_count} человек.
3. Сгруппируй продукты по категориям: овощи, мясо/рыба, бакалея, молочка, специи, напитки.
4. Если в меню есть готовые продукты (например, маринады, соленья) — укажи их в соответствующей категории.
5. Если продукт уже есть дома (указано в меню) — отметь это.
6. Выдай ТОЛЬКО список продуктов, без шагов, советов и таймлайнов.
7. Формат ответа: маркированный список, каждый пункт начинается с "- ".

Пример ответа:
- Куриное филе — 600 г (купить)
- Лук репчатый — 2 шт. (есть дома)
- Сметана — 200 г (купить)
"""
    user_content = f"Составь список покупок для этого меню на {people_count} человек."
    
    return call_routerai(system_prompt, user_content)

# ==============================================
#  ОБРАБОТЧИК УТОЧНЕНИЙ
# ==============================================
def handle_follow_up(prompt, last_response):
    """Обрабатывает уточнения к последнему ответу"""
    prompt_lower = prompt.lower()
    
    if "список" in prompt_lower and ("продуктов" in prompt_lower or "покупок" in prompt_lower):
        response = generate_shopping_list(last_response, 6)
        return response
    
    if "заменить" in prompt_lower:
        return "Чтобы заменить продукт, напишите: 'заменить [продукт] на [другой продукт]'"
    
    if "что" in prompt_lower or "как" in prompt_lower or "можно" in prompt_lower:
        return "Уточните, что именно вы хотите узнать: список покупок, замену продуктов, время приготовления или что-то другое?"
    
    return None

# ==============================================
#  ФУНКЦИЯ ДЛЯ ОТКРЫТИЯ РЕЦЕПТА В ЧАТЕ
# ==============================================
def open_recipe_in_chat(recipe_text):
    st.session_state.messages = [
        {"role": "assistant", "content": "Привет! Напиши, что у тебя сейчас и что хочешь получить. Я подберу рецепт.", "is_variant": False}
    ]
    st.session_state.messages.append({"role": "assistant", "content": recipe_text, "is_variant": True})
    st.session_state.selected_tab = "🏠 Главная"
    st.rerun()

# ==============================================
#  ФУНКЦИЯ ДЛЯ ГЕНЕРАЦИИ ПО БЫСТРОМУ СЦЕНАРИЮ
# ==============================================
def handle_quick_scenario(scenario):
    st.session_state.messages.append({"role": "user", "content": scenario, "is_variant": False})
    st.session_state.current_query = scenario
    st.session_state.variant_counter = 1
    st.session_state.rejected_variants = []
    st.session_state.previous_variants = []
    
    with st.spinner("Шеф думает..."):
        result = generate_scenario(scenario, 0, [])
        st.session_state.previous_variants.append(result)
        
        response = f"**Вариант 1**\n\n{result}"
        st.session_state.messages.append({"role": "assistant", "content": response, "is_variant": True})
        st.rerun()

# ==============================================
#  ФУНКЦИЯ ДЛЯ ГЕНЕРАЦИИ НОВОГО ВАРИАНТА
# ==============================================
def generate_next_variant():
    if st.session_state.variant_counter < 3:
        with st.spinner("Шеф думает над новым вариантом..."):
            previous_variants = st.session_state.previous_variants
            new_variant = generate_scenario(
                st.session_state.current_query,
                st.session_state.variant_counter,
                st.session_state.rejected_variants,
                previous_variants
            )
            st.session_state.variant_counter += 1
            st.session_state.rejected_variants.append(new_variant)
            st.session_state.previous_variants.append(new_variant)
            
            response = f"**Вариант {st.session_state.variant_counter}**\n\n{new_variant}"
            st.session_state.messages.append({"role": "assistant", "content": response, "is_variant": True})
            st.rerun()
    else:
        st.info("Все варианты просмотрены")

# ==============================================
#  ФУНКЦИЯ ДЛЯ ОБРАБОТКИ НОВОГО ЗАПРОСА
# ==============================================
def handle_new_query(prompt):
    st.session_state.messages.append({"role": "user", "content": prompt, "is_variant": False})
    st.session_state.current_query = prompt
    st.session_state.variant_counter = 1
    st.session_state.rejected_variants = []
    st.session_state.previous_variants = []
    
    with st.spinner("Шеф думает..."):
        result = generate_scenario(prompt, 0, [])
        st.session_state.previous_variants.append(result)
        
        response = f"**Вариант 1**\n\n{result}"
        st.session_state.messages.append({"role": "assistant", "content": response, "is_variant": True})
        st.rerun()

# ==============================================
#  ЧАТ-ИНТЕРФЕЙС (С КНОПКОЙ "СПИСОК ПОКУПОК")
# ==============================================
st.set_page_config(page_title="AI-Шеф", page_icon="🍳")

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Привет! Напиши, что у тебя сейчас и что хочешь получить. Я подберу рецепт.", "is_variant": False}
    ]
if "variant_counter" not in st.session_state:
    st.session_state.variant_counter = 0
if "current_query" not in st.session_state:
    st.session_state.current_query = ""
if "rejected_variants" not in st.session_state:
    st.session_state.rejected_variants = []
if "previous_variants" not in st.session_state:
    st.session_state.previous_variants = []
if "selected_tab" not in st.session_state:
    st.session_state.selected_tab = "🏠 Главная"

# ==============================================
#  БОКОВАЯ ПАНЕЛЬ / ВКЛАДКИ
# ==============================================
st.sidebar.title("🍳 AI-Шеф")
st.sidebar.markdown("---")

tabs = ["🏠 Главная", "📋 Рецепты", "🤔 Или повторим?", "👤 Профиль"]

try:
    current_index = tabs.index(st.session_state.selected_tab)
except ValueError:
    current_index = 0
    st.session_state.selected_tab = tabs[0]

tab = st.sidebar.radio("Меню", tabs, index=current_index)

if tab != st.session_state.selected_tab:
    st.session_state.selected_tab = tab
    st.rerun()

# ==============================================
#  ВКЛАДКА «ГЛАВНАЯ»
# ==============================================
if tab == "🏠 Главная":
    st.title("🍳 AI-Шеф")
    
    st.caption("⚡ Быстрые сценарии:")
    cols = st.columns(4)
    scenarios = [
        "Я в магазине, устал",
        "Гости через час",
        "Что на завтрак?",
        "План на неделю"
    ]
    for i, scenario in enumerate(scenarios):
        if cols[i].button(scenario):
            handle_quick_scenario(scenario)
    
    st.markdown("---")
    
    # Отображение чата с кнопками
    for idx, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            
            if message["role"] == "assistant" and message.get("is_variant", False):
                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.button("✅ Выбрать", key=f"choose_{idx}"):
                        full_text = message["content"]
                        recipe_name = extract_recipe_name(full_text)
                        save_user_history(
                            query=st.session_state.current_query,
                            chosen_recipe=recipe_name,
                            full_recipe=full_text,
                            situation_type="общий"
                        )
                        st.success(f"Сохранено: {recipe_name}")
                with col2:
                    if st.button("🔄 Ещё вариант", key=f"think_{idx}"):
                        generate_next_variant()
                with col3:
                    if st.button("🛒 Список покупок", key=f"shopping_{idx}"):
                        with st.spinner("Собираю список покупок..."):
                            shopping_list = generate_shopping_list(message["content"], 6)
                            st.session_state.messages.append({"role": "assistant", "content": shopping_list, "is_variant": False})
                            st.rerun()
    
    if prompt := st.chat_input("Опиши ситуацию или задай вопрос..."):
        st.session_state.messages.append({"role": "user", "content": prompt, "is_variant": False})
        
        if len(st.session_state.messages) > 1:
            last_assistant_response = None
            for msg in reversed(st.session_state.messages):
                if msg["role"] == "assistant" and msg.get("is_variant", False):
                    last_assistant_response = msg["content"]
                    break
            
            if last_assistant_response and is_follow_up(prompt):
                follow_up_response = handle_follow_up(prompt, last_assistant_response)
                if follow_up_response:
                    with st.chat_message("assistant"):
                        st.markdown(follow_up_response)
                        st.session_state.messages.append({"role": "assistant", "content": follow_up_response, "is_variant": False})
                    st.rerun()
                else:
                    handle_new_query(prompt)
            else:
                handle_new_query(prompt)
        else:
            handle_new_query(prompt)
    
    st.markdown("---")
    st.caption("🍳 AI-Шеф v1.0 — прототип")

# ==============================================
#  ВКЛАДКА «РЕЦЕПТЫ»
# ==============================================
elif tab == "📋 Рецепты":
    st.title("📋 Мои рецепты")
    
    history = get_user_history()
    if not history:
        st.info("У вас пока нет сохранённых рецептов. Начните готовить!")
    else:
        for i, session in enumerate(reversed(history)):
            recipe_name = session.get("chosen_recipe", "")
            full_recipe = session.get("full_recipe", recipe_name)
            date = session.get("date", "")
            if recipe_name:
                st.markdown(f"**{i+1}. {recipe_name}**")
                st.caption(f"Сохранено: {date}")
                if st.button("Посмотреть", key=f"view_{i}"):
                    open_recipe_in_chat(full_recipe)
                st.markdown("---")

# ==============================================
#  ВКЛАДКА «ИЛИ ПОВТОРИМ?»
# ==============================================
elif tab == "🤔 Или повторим?":
    st.title("🤔 Или повторим?")
    
    history = get_user_history()
    if not history:
        st.info("Вы ещё ничего не готовили. Начните прямо сейчас!")
    else:
        st.caption("Ваши последние выборы:")
        for i, session in enumerate(reversed(history[:5])):
            recipe_name = session.get("chosen_recipe", "")
            full_recipe = session.get("full_recipe", recipe_name)
            date = session.get("date", "")
            if recipe_name:
                st.markdown(f"**{i+1}. {recipe_name}**")
                st.caption(f"Последний раз: {date}")
                if st.button("Давай!", key=f"repeat_{i}"):
                    open_recipe_in_chat(full_recipe)
                st.markdown("---")

# ==============================================
#  ВКЛАДКА «ПРОФИЛЬ»
# ==============================================
elif tab == "👤 Профиль":
    st.title("👤 Профиль")
    
    history = get_user_history()
    st.metric("Всего рецептов", len(history))
    
    st.markdown("---")
    st.subheader("⛔ Я не ем")
    st.caption("Пока настройка отключена, но скоро будет доступна")
    
    st.markdown("---")
    st.subheader("🛒 Список покупок")
    st.caption("Скоро здесь появится список продуктов из ваших рецептов")