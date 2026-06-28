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

def get_user_profile():
    if not os.path.exists(HISTORY_FILE):
        return {}
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("profile", {})

def save_user_profile(profile):
    if not os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump({"sessions": [], "profile": {}}, f, ensure_ascii=False, indent=2)
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["profile"] = profile
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def save_user_history(query, chosen_recipe, full_recipe, situation_type, rating=None):
    history = get_user_history()
    for session in history:
        if session.get("chosen_recipe") == chosen_recipe:
            return
    
    if not os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump({"sessions": [], "profile": {}}, f, ensure_ascii=False, indent=2)

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

def log_substitution(original, replacement):
    profile = get_user_profile()
    if "substitutions" not in profile:
        profile["substitutions"] = []
    profile["substitutions"].append({
        "original": original,
        "replacement": replacement,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    save_user_profile(profile)

def log_budget(budget):
    profile = get_user_profile()
    profile["last_budget"] = budget
    save_user_profile(profile)

def log_people(people):
    profile = get_user_profile()
    profile["last_people"] = people
    save_user_profile(profile)

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

def extract_people_and_budget(text):
    """Извлекает количество человек и бюджет из текста"""
    text_lower = text.lower()
    people = None
    budget = None
    
    # Ищем "на 8 человек" или "на 8"
    people_match = re.search(r'на\s+(\d+)\s*(?:человек)?', text_lower)
    if people_match:
        people = int(people_match.group(1))
    
    # Ищем "бюджет 300" или "300 ₽" или "безлимит"
    budget_match = re.search(r'бюджет\s+(\d+)|(\d+)\s*[р₽]', text_lower)
    if budget_match:
        budget = int(budget_match.group(1) or budget_match.group(2))
    
    if 'безлимит' in text_lower:
        budget = 9999
    
    return people, budget

def format_recipe(text):
    """Парсит структурированный ответ AI"""
    lines = text.split('\n')
    
    title = "Рецепт"
    ingredients = []
    steps = []
    time = None
    budget = None
    
    current_section = None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        if line.startswith('Название:'):
            title = line.replace('Название:', '').strip()
        elif line.startswith('Время:'):
            time = re.search(r'(\d+)', line)
            time = time.group(1) if time else None
        elif line.startswith('Бюджет:'):
            budget = re.search(r'(\d+)', line)
            budget = budget.group(1) if budget else None
        elif line.startswith('Ингредиенты:'):
            current_section = 'ingredients'
        elif line.startswith('Шаги:'):
            current_section = 'steps'
        elif current_section == 'ingredients' and line.startswith('-'):
            ingredients.append(line[2:].strip())
        elif current_section == 'steps' and re.match(r'^\d+\.', line):
            steps.append(line)
    
    if not ingredients and not steps:
        return format_recipe_legacy(text)
    
    return {
        'title': title,
        'ingredients': ingredients,
        'steps': steps,
        'time': time,
        'budget': budget
    }

def format_recipe_legacy(text):
    lines = text.split('\n')
    
    title = "Рецепт"
    for line in lines:
        line = line.strip()
        if "Что приготовить:" in line:
            title = line.split("Что приготовить:")[1].strip()
            title = title.replace('###', '').strip()
            break
    
    if title == "Рецепт":
        for line in lines:
            line = line.strip()
            if line and not line.startswith(('Рецепт', '**', 'Список', 'Пошаговая', 'Время', 'Бюджет', 'Совет', 'Шаги', 'Ингредиенты', '#')):
                if not re.match(r'^[\d\s]+$', line) and not line.startswith('на'):
                    title = line
                    break
    
    ingredients = []
    for line in lines:
        line = line.strip()
        if line.startswith('-') or line.startswith('•') or line.startswith('*'):
            item = line[2:].strip()
            if item and len(item) < 100:
                ingredients.append(item)
    
    steps = []
    for line in lines:
        line = line.strip()
        if re.match(r'^\d+\.\s+', line):
            steps.append(line)
    
    time_match = re.search(r'(\d+)\s*мин', text)
    budget_match = re.search(r'(\d+)\s*[₽р]', text)
    
    return {
        'title': title,
        'ingredients': ingredients,
        'steps': steps,
        'time': time_match.group(1) if time_match else None,
        'budget': budget_match.group(1) if budget_match else None
    }

def display_formatted_recipe(text):
    recipe = format_recipe(text)
    
    st.markdown(f"## {recipe['title']}")
    
    meta_parts = []
    if recipe['time']:
        meta_parts.append(f"⏱️ {recipe['time']} мин")
    if recipe['budget']:
        meta_parts.append(f"💰 {recipe['budget']} ₽")
    if meta_parts:
        st.caption(" | ".join(meta_parts))
    
    if recipe['ingredients']:
        st.markdown("**Ингредиенты:**")
        col1, col2 = st.columns(2)
        for i, item in enumerate(recipe['ingredients']):
            if i % 2 == 0:
                col1.markdown(f"- {item}")
            else:
                col2.markdown(f"- {item}")
    
    if recipe['steps']:
        st.markdown("**Шаги:**")
        for step in recipe['steps']:
            st.markdown(step)
    
    if not recipe['ingredients'] and not recipe['steps']:
        st.markdown(text)

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
        "max_tokens": 6000
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
    substitutions = profile.get("substitutions", [])
    
    # Извлекаем настройки из текста запроса
    people_in_query, budget_in_query = extract_people_and_budget(query)
    
    default_people = profile.get("default_people", 2)
    default_budget = profile.get("default_budget", 300)
    
    if people_in_query:
        default_people = people_in_query
        profile["default_people"] = people_in_query
        save_user_profile(profile)
    if budget_in_query:
        default_budget = budget_in_query
        profile["default_budget"] = budget_in_query
        save_user_profile(profile)
    
    substitution_context = ""
    if substitutions:
        recent_subs = substitutions[-5:]
        sub_text = ", ".join([f"{s['original']} → {s['replacement']}" for s in recent_subs])
        substitution_context = f"\nУчти, что пользователь часто заменяет: {sub_text}. Если в рецепте есть {', '.join([s['original'] for s in recent_subs])}, предложи замены по умолчанию."

    previous_context = ""
    if previous_variants:
        previous_context = f"\nРанее я уже предлагал варианты: {', '.join(previous_variants)}.\nПредложи что-то другое, не повторяй их."

    is_week_plan = any(keyword in query.lower() for keyword in ["план на неделю", "меню на неделю", "неделя"])

    budget_context = f"\nБюджет на покупку продуктов: {default_budget} ₽. Количество человек: {default_people}. Старайся уложиться в бюджет."

    if is_week_plan:
        system_prompt = f"""
Ты — помощник по планированию питания. Пользователь хочет составить план питания на неделю.

Контекст:
- Он уже выбирал рецепты: {', '.join(chosen_recipes) if chosen_recipes else 'нет данных'}
- Его типичные ситуации: {', '.join(situation_types) if situation_types else 'нет данных'}
{substitution_context}
{budget_context}

Запрос пользователя: {query}

В начале ответа обязательно укажи бюджет и количество человек, на которые рассчитан план. Например: "План питания на {default_people} человек, бюджет {default_budget} ₽".

Твоя задача — составить чёткий план на неделю.

Алгоритм:
1. Определи, сколько человек будет питаться по плану (если не указано — {default_people} человек).
2. Определи бюджет (если не указано — {default_budget} ₽ на неделю).
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
{substitution_context}
{budget_context}

Запрос пользователя: {query}

В начале ответа обязательно укажи бюджет и количество человек, на которые рассчитано меню. Например: "Меню на {default_people} человек, бюджет {default_budget} ₽".

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
{substitution_context}
{budget_context}

Если он уже отклонял какие-то варианты в этом диалоге, не предлагай их снова.
{previous_context}

Ситуация пользователя: {query}

В начале ответа обязательно укажи бюджет и количество человек, на которые рассчитан рецепт. Например: "Рецепт на {default_people} человек, бюджет {default_budget} ₽".

Формат ответа должен быть строго таким:
Название: [название блюда]
Время: [число] мин
Бюджет: [число] ₽
Ингредиенты:
- [ингредиент 1] — [количество]
- [ингредиент 2] — [количество]
Шаги:
1. [шаг 1]
2. [шаг 2]

Не используй другие заголовки. Не добавляй лишних текстов. Только эта структура.

Алгоритм:
1. Определи ключевые параметры: время, бюджет, количество человек, состояние (устал, хочет впечатлить, планирует заранее), ограничения.
2. Если параметры не указаны, используй разумные значения по умолчанию.
3. Предложи ОДИН конкретный сценарий. Не давай альтернатив — только один вариант.
4. Учти контекст: если пользователь уже выбирал похожие блюда, предложи что-то новое или знакомое в зависимости от ситуации.

Тон: заботливый, дружелюбный, без давления. Не задавай лишних вопросов.
"""

    user_content = f"Запрос: {query}. Предложи вариант номер {variant_index + 1}"
    if rejected_variants:
        user_content += f". Не предлагай: {', '.join(rejected_variants)}"

    return call_routerai(system_prompt, user_content)

# ==============================================
#  ГЕНЕРАЦИЯ СПИСКА ПОКУПОК
# ==============================================
def generate_shopping_list(menu_text, people_count=2, budget=300):
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
6. Общая стоимость продуктов не должна превышать {budget} ₽. Если превышает — предложи замены, чтобы уложиться в бюджет.
7. Выдай ТОЛЬКО список продуктов, без шагов, советов и таймлайнов.
8. Формат ответа: маркированный список, каждый пункт начинается с "- ".

Пример ответа:
- Куриное филе — 600 г (купить) — ~200 ₽
- Лук репчатый — 2 шт. (есть дома)
- Сметана — 200 г (купить) — ~80 ₽
"""
    user_content = f"Составь список покупок для этого меню на {people_count} человек с бюджетом {budget} ₽."
    
    return call_routerai(system_prompt, user_content)

# ==============================================
#  ОБРАБОТЧИК УТОЧНЕНИЙ
# ==============================================
def handle_follow_up(prompt, last_response):
    prompt_lower = prompt.lower()
    
    if "заменить" in prompt_lower:
        match = re.search(r'заменить\s+([А-Яа-я\s]+)\s+на\s+([А-Яа-я\s]+)', prompt_lower)
        if match:
            original = match.group(1).strip()
            replacement = match.group(2).strip()
            log_substitution(original, replacement)
            return f"✅ Запомнил: заменяем **{original}** на **{replacement}**. В следующий раз буду предлагать с учётом этого."
        else:
            return "Чтобы заменить продукт, напишите: 'заменить [продукт] на [другой продукт]'"
    
    if "список" in prompt_lower and ("продуктов" in prompt_lower or "покупок" in prompt_lower):
        profile = get_user_profile()
        people = profile.get("default_people", 2)
        budget = profile.get("default_budget", 300)
        return generate_shopping_list(last_response, people, budget)
    
    if "?" in prompt or "сколько" in prompt_lower or "много" in prompt_lower or "мало" in prompt_lower or "можно" in prompt_lower or "как" in prompt_lower:
        profile = get_user_profile()
        people = profile.get("default_people", 2)
        system_prompt = f"""
Ты — помощник по кулинарии. Пользователь задаёт вопрос по текущему рецепту.

Рецепт, который пользователь смотрит:
{last_response}

Вопрос пользователя: {prompt}

Ответь на вопрос, учитывая контекст рецепта. Если вопрос о количестве ингредиента — уточни, на сколько человек рассчитан рецепт (по умолчанию {people}), и предложи корректировку.
Будь конкретным и дружелюбным. Не предлагай новый рецепт, если пользователь не просит.
"""
        return call_routerai(system_prompt, prompt)
    
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
        
        st.session_state.messages.append({"role": "assistant", "content": result, "is_variant": True})
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
            
            st.session_state.messages.append({"role": "assistant", "content": new_variant, "is_variant": True})
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
        
        st.session_state.messages.append({"role": "assistant", "content": result, "is_variant": True})
        st.rerun()

# ==============================================
#  ЧАТ-ИНТЕРФЕЙС
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
if "show_people_input" not in st.session_state:
    st.session_state.show_people_input = False

# ==============================================
#  БОКОВАЯ ПАНЕЛЬ / ВКЛАДКИ
# ==============================================
st.sidebar.title("🍳 AI-Шеф")
st.sidebar.markdown("---")

tabs = ["🏠 Главная", "🍲 Вкусненькое", "👤 Профиль"]

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
    
    st.caption("⚡ Быстро добавить настройки в запрос:")
    col1, col2 = st.columns(2)
    
    with col1:
        st.caption("👤 Человек")
        chip_cols = st.columns(5)
        people_options = ["2", "3", "4", "5"]
        for i, p in enumerate(people_options):
            with chip_cols[i]:
                if st.button(p, key=f"people_{p}"):
                    st.session_state.messages.append({"role": "user", "content": f"на {p} человек", "is_variant": False})
                    st.rerun()
        with chip_cols[4]:
            if st.button("6+", key="people_6plus"):
                st.session_state.show_people_input = True
                st.rerun()
    
    with col2:
        st.caption("💰 Бюджет")
        chip_cols = st.columns(4)
        budget_options = ["300 ₽", "500 ₽", "800 ₽", "Безлимит"]
        for i, b in enumerate(budget_options):
            with chip_cols[i]:
                if st.button(b, key=f"budget_{b}"):
                    st.session_state.messages.append({"role": "user", "content": f"бюджет {b}", "is_variant": False})
                    st.rerun()
    
    if st.session_state.show_people_input:
        st.markdown("---")
        st.caption("Введите количество человек (больше 6):")
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            custom_people = st.number_input(
                "",
                min_value=7,
                max_value=20,
                step=1,
                key="custom_people_input",
                label_visibility="collapsed"
            )
        with col2:
            if st.button("✅ Применить", key="apply_custom_people"):
                st.session_state.messages.append({"role": "user", "content": f"на {custom_people} человек", "is_variant": False})
                st.session_state.show_people_input = False
                st.rerun()
        with col3:
            if st.button("❌ Отмена", key="cancel_custom_people"):
                st.session_state.show_people_input = False
                st.rerun()
        st.markdown("---")
    
    st.markdown("---")
    
    for idx, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            if message["role"] == "assistant" and message.get("is_variant", False):
                display_formatted_recipe(message["content"])
            else:
                st.markdown(message["content"])
            
            if message["role"] == "assistant" and message.get("is_variant", False):
                col1, col2, col3 = st.columns([2, 1, 1])
                with col1:
                    if st.button("✅ Выбрать", key=f"choose_{idx}", use_container_width=True):
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
                    if st.button("🔄 Ещё", key=f"think_{idx}"):
                        generate_next_variant()
                with col3:
                    if st.button("🛒 Список", key=f"shopping_{idx}"):
                        with st.spinner("Собираю список покупок..."):
                            profile = get_user_profile()
                            people = profile.get("default_people", 2)
                            budget = profile.get("default_budget", 300)
                            shopping_list = generate_shopping_list(
                                message["content"],
                                people_count=people,
                                budget=budget
                            )
                            st.session_state.messages.append({"role": "assistant", "content": shopping_list, "is_variant": False})
                            st.rerun()
    
    # ---- ПОЛЕ ВВОДА И КНОПКА ОТПРАВКИ ----
    st.markdown("---")
    prompt = st.text_area(
        "Опиши ситуацию или задай вопрос...",
        value="",
        key="chat_input_text",
        height=68,
        placeholder="Например: что приготовить из курицы и риса?"
    )
    
    col1, col2 = st.columns([4, 1])
    with col2:
        if st.button("Отправить", key="send_message", use_container_width=True):
            if st.session_state.chat_input_text:
                prompt_text = st.session_state.chat_input_text
                
                # Добавляем сообщение пользователя в чат
                st.session_state.messages.append({"role": "user", "content": prompt_text, "is_variant": False})
                st.session_state.input_buffer = ""
                
                # Собираем ВСЕ сообщения пользователя в текущем диалоге
                full_query = ""
                for msg in st.session_state.messages:
                    if msg["role"] == "user" and not msg.get("is_variant", False):
                        full_query += msg["content"] + " "
                full_query = full_query.strip()
                
                # Проверяем, является ли это уточнением к последнему ответу
                if len(st.session_state.messages) > 1:
                    last_assistant_response = None
                    for msg in reversed(st.session_state.messages):
                        if msg["role"] == "assistant" and msg.get("is_variant", False):
                            last_assistant_response = msg["content"]
                            break
                    
                    if last_assistant_response:
                        follow_up_response = handle_follow_up(prompt_text, last_assistant_response)
                        if follow_up_response:
                            with st.chat_message("assistant"):
                                st.markdown(follow_up_response)
                                st.session_state.messages.append({"role": "assistant", "content": follow_up_response, "is_variant": False})
                            st.rerun()
                        else:
                            # Передаём full_query в generate_scenario
                            handle_new_query(full_query)
                    else:
                        handle_new_query(full_query)
                else:
                    handle_new_query(full_query)
                st.rerun()
    
    st.markdown("---")
    st.caption("🍳 AI-Шеф v1.0 — прототип")

# ==============================================
#  ВКЛАДКА «ВКУСНЕНЬКОЕ»
# ==============================================
elif tab == "🍲 Вкусненькое":
    st.title("🍲 Моё вкусненькое")
    
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
#  ВКЛАДКА «ПРОФИЛЬ»
# ==============================================
elif tab == "👤 Профиль":
    st.title("👤 Профиль")
    
    history = get_user_history()
    st.metric("Всего рецептов", len(history))
    
    profile = get_user_profile()
    substitutions = profile.get("substitutions", [])
    if substitutions:
        st.markdown("---")
        st.subheader("🔄 Ваши замены")
        for sub in substitutions[-5:]:
            st.caption(f"{sub['original']} → {sub['replacement']} ({sub['date'][:10]})")
    
    default_people = profile.get("default_people")
    default_budget = profile.get("default_budget")
    if default_people or default_budget:
        st.markdown("---")
        st.subheader("📊 Ваши настройки по умолчанию")
        if default_people:
            st.caption(f"👤 Обычно готовите на {default_people} человек")
        if default_budget:
            st.caption(f"💰 Обычный бюджет: {default_budget} ₽")
    
    st.markdown("---")
    st.subheader("⛔ Я не ем")
    st.caption("Пока настройка отключена, но скоро будет доступна")
    
    st.markdown("---")
    st.subheader("🛒 Список покупок")
    st.caption("Скоро здесь появится список продуктов из ваших рецептов")