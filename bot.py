import os
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
)
import requests
from datetime import datetime
import matplotlib.pyplot as plt
import io
from deep_translator import GoogleTranslator

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)



WEIGHT, HEIGHT, AGE, GENDER, ACTIVITY, CITY, FOOD_AMOUNT, WORKOUT_TYPE, WORKOUT_DURATION = range(9)

users = {}

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', 'TELEGRAM_TOKEN')
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY', 'WEATHER_API_KEY')
NINJAS_API_KEY = os.getenv('NINJAS_API_KEY', 'NINJAS_API_KEY')


async def logging_middleware(update, context):
    user = update.effective_user
    
    if update.message:
        logger.info(
            f"User {user.id} (@{user.username}) | "
            f"Message: {update.message.text}"
        )
    elif update.callback_query:
        logger.info(
            f"User {user.id} (@{user.username}) | "
            f"Callback: {update.callback_query.data}"
        )
    
    return None

def translate_to_english(text):
    try:
        translator = GoogleTranslator(source='auto', target='en')
        translated = translator.translate(text)
        return translated
    except Exception as e:
        logger.error(f"Translation error: {e}")
        return text

def get_weather(city):
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data['main']['temp']
        return None
    except Exception as e:
        logger.error(f"Weather API error: {e}")
        return None

def calculate_water_goal(weight, activity_minutes, temperature):
    base = weight * 30
    activity_bonus = (activity_minutes // 30) * 500
    temp_bonus = 0
    if temperature and temperature > 25:
        temp_bonus = 750
    elif temperature and temperature > 20:
        temp_bonus = 500
    return base + activity_bonus + temp_bonus

def calculate_calorie_goal(weight, height, age, gender, activity_minutes):
    if gender == 'М':
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    else:
        bmr = 10 * weight + 6.25 * height - 5 * age - 161
    
    activity_bonus = (activity_minutes / 30) * 250
    return int(bmr + activity_bonus)

def get_calories_burned(activity, duration_minutes, weight):
    try:
        activity_en = translate_to_english(activity)
        url = f"https://api.api-ninjas.com/v1/caloriesburned?activity={activity_en}"
        headers = {'X-Api-Key': NINJAS_API_KEY}
        response = requests.get(url, headers=headers, timeout=20)
        
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                calories_per_minute = data[0]['calories_per_hour'] / 60
                adjusted_calories = calories_per_minute * (weight / 70)
                return int(adjusted_calories * duration_minutes)
        return int(duration_minutes * 5 * (weight / 70))
    except Exception as e:
        logger.error(f"Calories burned API error: {e}")
        return int(duration_minutes * 5 * (weight / 70))

def get_food_calories(food_name):
    try:
        food_en = translate_to_english(food_name)
        url = f"https://world.openfoodfacts.org/cgi/search.pl?search_terms={food_en}&json=true"
        response = requests.get(url, timeout=600)
        
        if response.status_code == 200:
            data = response.json()
            if data['products']:
                product = data['products'][0]
                calories = product.get('nutriments', {}).get('energy-kcal_100g', 0)
                return {
                    'name': product.get('product_name', food_name),
                    'calories': calories,
                    'serving_size': 100
                }
    except Exception as e:
        logger.error(f"OpenFoodFacts API error: {e}")
    
    return None

def init_user_data(user_id):
    if user_id not in users:
        users[user_id] = {
            'weight': None,
            'height': None,
            'age': None,
            'gender': None,
            'activity': None,
            'city': None,
            'water_goal': None,
            'calorie_goal': None,
            'logged_water': 0,
            'logged_calories': 0,
            'burned_calories': 0,
            'water_history': [],
            'calorie_history': [],
            'temp_food_data': None
        }

async def start(update, context):
    user_id = update.effective_user.id
    init_user_data(user_id)
    
    await update.message.reply_text(
        "Доступные команды:\n"
        "/set_profile - Настроить профиль\n"
        "/log_water - Записать выпитую воду\n"
        "/log_food - Записать съеденную еду\n"
        "/log_workout - Записать тренировку\n"
        "/check_progress - Проверить прогресс\n"
        "/show_graphs - Показать графики прогресса\n"
        "/help - Помощь"
    )

async def help_command(update, context):
    await update.message.reply_text(
        "/set_profile - Укажите вес, рост, возраст, пол, активность и город\n"
        "/log_water <мл> - Например: /log_water 250\n"
        "/log_food <название> - Например: /log_food банан\n"
        "/log_workout <тип> <минуты> - Например: /log_workout бег 30\n"
        "/check_progress - Посмотреть текущий прогресс\n"
        "/show_graphs - Графики прогресса за день"
    )

async def set_profile(update, context):
    user_id = update.effective_user.id
    init_user_data(user_id)
    
    await update.message.reply_text(
        "Настройка профиля\n\n"
        "Введите ваш вес (в кг):"
    )
    return WEIGHT

async def weight_handler(update, context):
    user_id = update.effective_user.id
    try:
        weight = float(update.message.text)
        users[user_id]['weight'] = weight
        await update.message.reply_text("Введите ваш рост (в см):")
        return HEIGHT
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите корректное число:")
        return WEIGHT

async def height_handler(update, context):
    user_id = update.effective_user.id
    try:
        height = float(update.message.text)
        users[user_id]['height'] = height
        await update.message.reply_text("Введите ваш возраст:")
        return AGE
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите корректное число:")
        return HEIGHT

async def age_handler(update, context):
    user_id = update.effective_user.id
    try:
        age = int(update.message.text)
        users[user_id]['age'] = age
        await update.message.reply_text(
            "Укажите ваш пол:",
            reply_markup=ReplyKeyboardMarkup([['М', 'Ж']], one_time_keyboard=True)
        )
        return GENDER
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите корректное число:")
        return AGE

async def gender_handler(update, context):
    user_id = update.effective_user.id
    gender = update.message.text
    
    if gender not in ['М', 'Ж']:
        await update.message.reply_text("Пожалуйста, выберите М или Ж:")
        return GENDER
    
    users[user_id]['gender'] = gender
    await update.message.reply_text(
        "Сколько минут активности у вас в день?",
        reply_markup=ReplyKeyboardRemove()
    )
    return ACTIVITY

async def activity_handler(update, context):
    user_id = update.effective_user.id
    try:
        activity = int(update.message.text)
        users[user_id]['activity'] = activity
        await update.message.reply_text("В каком городе вы находитесь?")
        return CITY
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите корректное число:")
        return ACTIVITY

async def city_handler(update, context):
    user_id = update.effective_user.id
    city = update.message.text
    users[user_id]['city'] = city
    
    temperature = get_weather(city)
    temp_text = f"{temperature}°C" if temperature else "не определена"
    
    user_data = users[user_id]
    water_goal = calculate_water_goal(
        user_data['weight'],
        user_data['activity'],
        temperature
    )
    calorie_goal = calculate_calorie_goal(
        user_data['weight'],
        user_data['height'],
        user_data['age'],
        user_data['gender'],
        user_data['activity']
    )
    
    users[user_id]['water_goal'] = water_goal
    users[user_id]['calorie_goal'] = calorie_goal
    users[user_id]['logged_water'] = 0
    users[user_id]['logged_calories'] = 0
    users[user_id]['burned_calories'] = 0
    
    
    await update.message.reply_text(
        f"Ваши параметры:\n"
        f"Вес: {user_data['weight']} кг\n"
        f"Рост: {user_data['height']} см\n"
        f"Возраст: {user_data['age']} лет\n"
        f"Пол: {user_data['gender']}\n"
        f"Активность: {user_data['activity']} мин/день\n"
        f"Город: {city}\n"
        f"Температура: {temp_text}\n\n"
        f"Норма воды: {water_goal} мл\n"
        f"Норма калорий: {calorie_goal} ккал"
    )
    return ConversationHandler.END

async def cancel(update, context):
    await update.message.reply_text(
        "Настройка отменена.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

async def log_water(update, context):
    user_id = update.effective_user.id
    init_user_data(user_id)
    
    if not users[user_id]['water_goal']:
        await update.message.reply_text(
            "Сначала настройте профиль командой /set_profile"
        )
        return
    
    try:
        amount = int(context.args[0]) if context.args else 0
        if amount <= 0:
            raise ValueError
        
        users[user_id]['logged_water'] += amount
        remaining = users[user_id]['water_goal'] - users[user_id]['logged_water']
        
        users[user_id]['water_history'].append({
            'time': datetime.now(),
            'amount': users[user_id]['logged_water']
        })
        
        
        if remaining <= 0:
            await update.message.reply_text(
                f"Записано: {amount} мл\n"
                f"Вы выполнили дневную норму воды"
            )
        else:
            await update.message.reply_text(
                f"Записано: {amount} мл\n"
                f"Выпито: {users[user_id]['logged_water']} мл из {users[user_id]['water_goal']} мл\n"
                f"Осталось: {remaining} мл"
            )
    except (IndexError, ValueError):
        await update.message.reply_text(
            "Используйте: /log_water <количество в мл>\n"
            "Например: /log_water 250"
        )

async def log_food_start(update, context):
    user_id = update.effective_user.id
    init_user_data(user_id)
    
    if not users[user_id]['calorie_goal']:
        await update.message.reply_text(
            "Сначала настройте профиль командой /set_profile"
        )
        return ConversationHandler.END
    
    if not context.args:
        await update.message.reply_text(
            "Используйте: /log_food <название продукта>\n"
            "Например: /log_food банан"
        )
        return ConversationHandler.END
    
    food_name = ' '.join(context.args)
    await update.message.reply_text(f"Ищу информацию о '{food_name}'...")
    
    food_data = get_food_calories(food_name)
    
    if not food_data:
        await update.message.reply_text(
            f"Не удалось найти информацию о '{food_name}'. "
            f"Попробуйте другое название."
        )
        return ConversationHandler.END
    
    users[user_id]['temp_food_data'] = food_data
    
    await update.message.reply_text(
        f"{food_data['name'].capitalize()}\n"
        f"Калории: {food_data['calories']} ккал на {food_data['serving_size']} г\n\n"
        f"Сколько грамм вы съели?"
    )
    
    return FOOD_AMOUNT

async def food_amount_handler(update, context):
    user_id = update.effective_user.id
    
    try:
        amount = float(update.message.text)
        if amount <= 0:
            raise ValueError
        
        food_data = users[user_id]['temp_food_data']
        calories = (food_data['calories'] / food_data['serving_size']) * amount
        
        users[user_id]['logged_calories'] += calories
        
        users[user_id]['calorie_history'].append({
            'time': datetime.now(),
            'amount': users[user_id]['logged_calories']
        })
        

        await update.message.reply_text(
            f"Записано: {calories:.1f} ккал\n"
            f"Потреблено: {users[user_id]['logged_calories']:.1f} ккал\n"
            f"Осталось до цели: {users[user_id]['calorie_goal'] - users[user_id]['logged_calories'] + users[user_id]['burned_calories']:.1f} ккал"
        )
        
        users[user_id]['temp_food_data'] = None
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите корректное число:")
        return FOOD_AMOUNT

async def log_workout_start(update, context):
    user_id = update.effective_user.id
    init_user_data(user_id)
    
    if not users[user_id]['calorie_goal']:
        await update.message.reply_text(
            "Сначала настройте профиль командой /set_profile"
        )
        return ConversationHandler.END
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "Используйте: /log_workout <тип тренировки> <минуты>\n"
            "Например: /log_workout бег 30"
        )
        return ConversationHandler.END
    
    try:
        duration = int(context.args[-1])
        workout_type = ' '.join(context.args[:-1])
        
        if duration <= 0:
            raise ValueError
        
        weight = users[user_id]['weight']
        calories_burned = get_calories_burned(workout_type, duration, weight)
        
        users[user_id]['burned_calories'] += calories_burned

        users[user_id]['calorie_history'].append({
            'time': datetime.now(),
            'amount': -users[user_id]['burned_calories']
        })

        users[user_id]['water_history'].append({
            'time': datetime.now(),
            'amount': (duration // 30) * -200
        })
        
        
        
        await update.message.reply_text(
            f"{workout_type.capitalize()} {duration} минут\n"
            f"Сожжено: {calories_burned} ккал\n"
            f"Дополнительно выпейте: {(duration // 30) * 200} мл воды\n\n"
            f"Можно съесть ещё: {users[user_id]['calorie_goal'] - users[user_id]['logged_calories'] + users[user_id]['burned_calories']:.1f} ккал"
        )
        
        return ConversationHandler.END
        
    except (ValueError, IndexError):
        await update.message.reply_text(
            "Используйте: /log_workout <тип тренировки> <минуты>\n"
            "Например: /log_workout бег 30"
        )
        return ConversationHandler.END

async def check_progress(update, context):
    user_id = update.effective_user.id
    init_user_data(user_id)
    
    if not users[user_id]['water_goal']:
        await update.message.reply_text(
            "Сначала настройте профиль командой /set_profile"
        )
        return
    
    user_data = users[user_id]
    water_remaining = user_data['water_goal'] - user_data['logged_water']
    calorie_balance = user_data['logged_calories'] - user_data['burned_calories']
    calorie_remaining = user_data['calorie_goal'] - calorie_balance
    
    
    
    await update.message.reply_text(
        f"Прогресс:\n\n"
        f"Вода:\n"
        f"- Выпито: {user_data['logged_water']} мл из {user_data['water_goal']} мл\n"
        f"- Осталось: {max(0, water_remaining)} мл\n\n"
        f"Калории:\n"
        f"- Потреблено: {user_data['logged_calories']:.1f} ккал\n"
        f"- Сожжено: {user_data['burned_calories']:.1f} ккал\n"
        f"- Баланс: {calorie_balance:.1f} ккал\n"
        f"- Осталось до цели: {calorie_remaining:.1f} ккал"
    )

async def show_graphs(update, context):
    user_id = update.effective_user.id
    init_user_data(user_id)
    
    if not users[user_id]['water_goal']:
        await update.message.reply_text(
            "Сначала настройте профиль командой /set_profile"
        )
        return
    
    user_data = users[user_id]
    
    if not user_data['water_history'] and not user_data['calorie_history']:
        await update.message.reply_text(
            "Пока нет данных для графиков. Начните логировать воду и еду!"
        )
        return
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
    
    if user_data['water_history']:
        times = [entry['time'] for entry in user_data['water_history']]
        amounts = [entry['amount'] for entry in user_data['water_history']]
        
        ax1.plot(times, amounts, marker='o', linewidth=2.5, markersize=8, 
                 color='#3498db', label='Выпито воды')
        ax1.axhline(y=user_data['water_goal'], color='#2ecc71', linestyle='--', 
                    linewidth=2, label=f"Цель: {user_data['water_goal']} мл")
        ax1.fill_between(times, amounts, alpha=0.2, color='#3498db')
        
        current_water = user_data['logged_water']
        
        ax1.text(0.02, 0.98, 
                 f"Текущий объём: {current_water} мл ({(current_water / user_data['water_goal']) * 100:.1f}%)\n"
                 f"Осталось: {max(0, user_data['water_goal'] - current_water)} мл",
                 transform=ax1.transAxes,
                 fontsize=11,
                 verticalalignment='top',
                 bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
        
        ax1.set_ylabel('Вода (мл)', fontsize=13, fontweight='bold')
        ax1.set_title('Прогресс по воде', fontsize=15, fontweight='bold', pad=15)
        ax1.legend(fontsize=11, loc='upper right')
        ax1.grid(True, alpha=0.3, linestyle='--')
    else:
        ax1.text(0.5, 0.5, 'Нет данных о воде', ha='center', va='center', 
                 transform=ax1.transAxes, fontsize=14)
        ax1.set_title('Прогресс по воде', fontsize=15, fontweight='bold', pad=15)
    
    if user_data['calorie_history']:
        times = [entry['time'] for entry in user_data['calorie_history']]
        consumed = [entry['amount'] for entry in user_data['calorie_history']]
        
        ax2.plot(times, consumed, marker='s', linewidth=2.5, markersize=8, 
                 color='#e74c3c', label='Потреблено', zorder=3)
        ax2.fill_between(times, consumed, alpha=0.2, color='#e74c3c')
        
        burned = user_data['burned_calories']
        net_calories = [c - burned for c in consumed]
        ax2.plot(times, net_calories, marker='o', linewidth=2.5, markersize=8,
                 color='#9b59b6', label='Чистый баланс', linestyle='--', zorder=3)
        
        ax2.axhline(y=user_data['calorie_goal'], color='#2ecc71', linestyle='--',
                    linewidth=2, label=f"Цель: {user_data['calorie_goal']} ккал", zorder=2)
        
        if burned > 0:
            ax2.fill_between(times, consumed, net_calories, 
                            alpha=0.3, color='#f39c12', 
                            label=f'Сожжено: {burned:.0f} ккал')
        
        current_net = user_data['logged_calories'] - burned
        
        stats_text = (
            f"Потреблено: {user_data['logged_calories']:.0f} ккал\n"
            f'Сожжено: {burned:.0f} ккал\n'
            f"Баланс: {current_net:.0f} ккал ({(current_net / user_data['calorie_goal']) * 100:.1f}%)\n"
            f"Осталось: {user_data['calorie_goal'] - current_net:.0f} ккал"
        )
        
        ax2.text(0.02, 0.98, stats_text,
                 transform=ax2.transAxes,
                 fontsize=11,
                 verticalalignment='top',
                 bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
        
        ax2.set_ylabel('Калории (ккал)', fontsize=13, fontweight='bold')
        ax2.set_xlabel('Время', fontsize=13, fontweight='bold')
        ax2.set_title('Прогресс по калориям', fontsize=15, fontweight='bold', pad=15)
        ax2.legend(fontsize=11, loc='upper right')
        ax2.grid(True, alpha=0.3, linestyle='--')
    else:
        ax2.text(0.5, 0.5, 'Нет данных о калориях', ha='center', va='center',
                 transform=ax2.transAxes, fontsize=14)
        ax2.set_title('Прогресс по калориям', fontsize=15, fontweight='bold', pad=15)
    
    plt.tight_layout()
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=120, bbox_inches='tight')
    buf.seek(0)
    plt.close()
    
    caption = "Ваш прогресс за сегодня\n\n"
    
    if user_data['water_history']:
        caption += f"Вода: {(user_data['logged_water'] / user_data['water_goal']) * 100:.0f}% выполнено\n"
    
    if user_data['calorie_history']:
        caption += f"Калории: {((user_data['logged_calories'] - user_data['burned_calories']) / user_data['calorie_goal']) * 100:.0f}% от цели"
    
    await update.message.reply_photo(
        photo=buf,
        caption=caption
    )

def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(
        MessageHandler(filters.ALL, logging_middleware),
        group=-1  
    )

    profile_conv = ConversationHandler(
        entry_points=[CommandHandler('set_profile', set_profile)],
        states={
            WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, weight_handler)],
            HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, height_handler)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, age_handler)],
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, gender_handler)],
            ACTIVITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, activity_handler)],
            CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, city_handler)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    food_conv = ConversationHandler(
        entry_points=[CommandHandler('log_food', log_food_start)],
        states={
            FOOD_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, food_amount_handler)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(profile_conv)
    application.add_handler(CommandHandler('log_water', log_water))
    application.add_handler(food_conv)
    application.add_handler(CommandHandler('log_workout', log_workout_start))
    application.add_handler(CommandHandler('check_progress', check_progress))
    application.add_handler(CommandHandler('show_graphs', show_graphs))
    
    logger.info("bot started")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
