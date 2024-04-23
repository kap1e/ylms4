import sqlite3
import logging
import datetime
import re
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyflightdata import FlightData



"""
ТЕХНИЧЕСКИЕ ДАННЫЕ
"""
API_TOKEN = ''
DB_PATH = 'flights.db'

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота, диспетчера и хранилища состояний
storage = MemoryStorage()
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=storage)

# Инициализация api FlightRadar
fr = FlightData()

# Определение состояний
class Form(StatesGroup):
    main_menu = State()  # Главный экран с кнопками
    about_us = State()   # Экран "О нас"
    about_you = State()  # Экран "О вас"
    flight_info = State()  # Экран для запроса информации о рейсе
    viewing_flights = State()  # Экран просмотра рейсов пользователя
    airport_info = State()  # Экран для информации об аэропорте
    waiting_for_flight_number = State()
    waiting_for_flight_date = State()






"""
КЛАВИАТУРА
"""
# Создание клавиатуры главного меню
def main_menu_keyboard():
    keyboard_markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    buttons = ["Добавить рейс", "Найти аэропорт", "Ваши рейсы", "Информация о рейсе", "О вас", "О нас"]
    keyboard_markup.add(*(types.KeyboardButton(text) for text in buttons))
    return keyboard_markup

# Клавиатура для кнопки "Назад"
back_button_keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True).add(types.KeyboardButton("Назад"))







"""
ИНСТРУМЕНТЫ ДЛЯ {ВАШИ РЕЙСЫ}
"""
# Создание и подключение к базе данных
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS flights (user_id INTEGER PRIMARY KEY, flights TEXT)''')
conn.commit()

# Функция для получения рейсов пользователя
def get_user_flights(user_id):
    c.execute("SELECT flights FROM flights WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    if result:
        return result[0]
    return None

# Функция для разбивки рейсов на страницы
def paginate_flights(flights, page, per_page=5):
    flights = flights.split('; ')
    page_count = (len(flights) + per_page - 1) // per_page  # Получаем количество страниц
    current_flights = flights[(page - 1) * per_page:page * per_page]
    return current_flights, page, page_count

# Клавиатура для навигации по страницам
def navigation_markup(page, page_count):
    buttons = [
        InlineKeyboardButton("Прошлая", callback_data=f"prev_{page}"),
        InlineKeyboardButton(f"{page} из {page_count}", callback_data="current_page"),
        InlineKeyboardButton("Далее", callback_data=f"next_{page}")
    ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons])







"""
ОБРАБОТЧИКИ КОМАНД
"""
# Обработчик команды /start
@dp.message_handler(commands=['start'], state='*')
async def send_welcome(message: types.Message, state: FSMContext):
    await Form.main_menu.set()
    await message.reply("Привет! Я твой помощник в сфере полетов:", reply_markup=main_menu_keyboard())

@dp.message_handler(lambda message: message.text == "Назад", state=[Form.about_us, Form.about_you, Form.flight_info, Form.viewing_flights, Form.airport_info, Form.waiting_for_flight_date, Form.waiting_for_flight_number])
async def handle_back_button(message: types.Message, state: FSMContext):
    await Form.main_menu.set()
    await message.answer("Возвращаемся в главное меню.", reply_markup=main_menu_keyboard())

# Обработчик нажатий на кнопки в главном меню
@dp.message_handler(lambda message: message.text in ["Добавить рейс", "Найти аэропорт", "Ваши рейсы", "Информация о рейсе", "О вас", "О нас"], state=Form.main_menu)
async def handle_main_menu_buttons(message: types.Message, state: FSMContext):
    selected_option = message.text
    if selected_option == "Информация о рейсе":
        await Form.flight_info.set()
        await message.answer("Пожалуйста, введите номер рейса или нажмите на кнопку Назад", reply_markup=back_button_keyboard)
    elif selected_option == "О нас":
        await Form.about_us.set()
        await message.answer("Мы команда энтузиастов без высшего образования. Мы создали этого бота чтобы помочь вам в вашем авиапутешествии по миру.", reply_markup=back_button_keyboard)
    elif selected_option == "О вас":
        await Form.about_you.set()
        await message.answer("Этот раздел позволяет узнать информацию о вашем аккаунте и настройках.", reply_markup=back_button_keyboard)
    elif selected_option == "Ваши рейсы":
        await show_flights(message, state)
    elif selected_option == "Найти аэропорт":
        await Form.airport_info.set()
        await message.answer("Пожалуйста, введите номер аэропорта или нажмите на кнопку Назад", reply_markup=back_button_keyboard)
    elif selected_option == "Добавить рейс":
        await flight_add_start(message)








# Обработчик для начала добавления рейса
@dp.message_handler(lambda message: message.text.lower() == "добавить рейс", state=Form.main_menu)
async def flight_add_start(message: types.Message):
    await Form.waiting_for_flight_number.set()
    await message.answer("Введите номер рейса:", reply_markup=back_button_keyboard)

# Обработчик для номера рейса
@dp.message_handler(state=Form.waiting_for_flight_number)
async def flight_number_received(message: types.Message, state: FSMContext):
    # Сохраняем номер рейса во временном хранилище состояний
    async with state.proxy() as data:
        data['flight_number'] = message.text
    await Form.next()
    await message.answer("Введите дату рейса в формате DD-MM-YYYY:", reply_markup=back_button_keyboard)

# Обработчик для даты рейса
@dp.message_handler(lambda message: re.match(r"\d{2}-\d{2}-\d{4}", message.text), state=Form.waiting_for_flight_date)
async def flight_date_received(message: types.Message, state: FSMContext):
    try:
        flight_date = datetime.datetime.strptime(message.text, '%d-%m-%Y')
        if flight_date < datetime.datetime.now():
            await message.answer("Дата не может быть в прошлом. Пожалуйста, введите корректную дату:", reply_markup=back_button_keyboard)
            return
        async with state.proxy() as data:
            data['flight_date'] = flight_date
        # Здесь код для запроса к FlightradarAPI
        info = fr.get_flight_for_date(data['flight_number'], data['flight_date'].strftime('%Y%m%d'))[0]
        dep_date = datetime.datetime.strptime(info['time']['scheduled']['departure_date'], '%Y%m%d').date()
        or_ap = info['airport']['origin']['name']
        dest_ap = info['airport']['destination']['name']
        ac_reg = info['aircraft']['registration']
        dep_time = datetime.datetime.strptime(info['time']['scheduled']['departure_time'], '%H%M').time()
        ar_time = datetime.datetime.strptime(info['time']['scheduled']['arrival_time'], '%H%M').time()
        flight_info = {'dep_date': dep_date, 'or_ap': or_ap, 'dest_ap': dest_ap, 'ac_reg': ac_reg, 'dep_time': dep_time, 'ar_time': ar_time}
        flight_info_message = f"Дата отправления: {dep_date.strftime('%Y%m%d')} \n Время отправления: {dep_time}\n Время прибытия: {ar_time}\n Откуда: {or_ap}\n Куда: {dest_ap}\n Номер самолета: {ac_reg}"
        # Проверяем, есть ли информация о рейсе
        if flight_info:
            await message.answer(f"Информация о рейсе: {flight_info_message}", reply_markup=back_button_keyboard)
            # Добавляем информацию о рейсе в базу данных
            user_id = message.from_user.id
            add_flight_to_db(user_id, data['flight_number'], data['flight_date'], flight_info_message)
            await message.answer("Рейс добавлен.", reply_markup=back_button_keyboard)
        else:
            await message.answer("Информация о рейсе не найдена, попробуйте другой номер рейса.", reply_markup=back_button_keyboard)
            await Form.waiting_for_flight_number.set()

    except ValueError:
        # Сообщаем пользователю, что формат даты некорректен
        await message.reply("Неправильный формат даты. Пожалуйста, введите дату в формате DD-MM-YYYY:", reply_markup=back_button_keyboard)


@dp.message_handler(state=Form.waiting_for_flight_date)
async def flight_date_invalid(message: types.Message):
    await message.answer("Неправильный формат даты, пожалуйста, введите дату в формате DD-MM-YYYY:", reply_markup=back_button_keyboard)

def add_flight_to_db(user_id, flight_number, flight_date, flight_info):
    # Добавляем или обновляем информацию в базе данных
    existing_flights = get_user_flights(user_id)
    new_flight_record = f"{flight_number} : {flight_info}; "
    if existing_flights:
        updated_flights = existing_flights + new_flight_record
    else:
        updated_flights = new_flight_record
    c.execute("INSERT OR REPLACE INTO flights (user_id, flights) VALUES (?, ?)", (user_id, updated_flights))
    conn.commit()








# Обработчик ввода номера рейса
@dp.message_handler(state=Form.flight_info)
async def process_flight_info(message: types.Message, state: FSMContext):
    if message.text.lower() == "назад":
        await Form.main_menu.set()
        await message.answer("Возвращаемся в главное меню.", reply_markup=main_menu_keyboard())
    else:
        flight_number = message.text
        info = fr.get_history_by_flight_number(flight_number)[-1]
        dep_date = datetime.datetime.strptime(info['time']['real']['departure_date'], '%Y%m%d').date()
        or_ap = info['airport']['origin']['name']
        dest_ap = info['airport']['destination']['name']
        ac_model = info['aircraft']['model']['code']
        ac_reg = info['aircraft']['registration']
        dep_time = datetime.datetime.strptime(info['time']['real']['departure_time'], '%H%M').time()
        ar_time = datetime.datetime.strptime(info['time']['real']['arrival_time'], '%H%M').time()
        response = (f"Информация для последнего маршрута рейса {flight_number}:""\n"
                    f"🗓Дата: {dep_date.strftime('%d.%m.%Y')}""\n"
                    f"🛫Отправление: {dep_time.strftime('%H:%M')} 🛬Прибытие: {ar_time.strftime('%H:%M')}""\n"
                    f"🛫Вылет из {or_ap}          🛬В {dest_ap}""\n"
                    f"✈️Cамолёт: {ac_model} номер: {ac_reg}")
        await message.answer(response, reply_markup=back_button_keyboard)


@dp.message_handler(state=Form.airport_info)
async def process_airport_info(message: types.Message, state: FSMContext):
    if message.text.lower() == "назад":
        await Form.main_menu.set()
        await message.answer("Возвращаемся в главное меню.", reply_markup=main_menu_keyboard())
    else:
        airport_name = message.text
        info = fr.get_airport_details(airport_name)
        response = (f"🛩Информация для аэропорта {airport_name} здесь.\n"
        f'Полное название: {info["name"]}\n'
        f'Код ICAO: {info["code"]["icao"]}\n'
        f'Код IATA: {info["code"]["iata"]}\n'
        f'⏳Индекс задержки на прибытие: {info["delayIndex"]["arrivals"]}\n'
        f'⏳Индекс задержки на отправление: {info["delayIndex"]["departures"]}\n')
        await message.answer(response, reply_markup=back_button_keyboard)


# Обработчик команды /flights и просмотр рейсов
async def show_flights(message: types.Message, state: FSMContext):
    user_flights = get_user_flights(message.from_user.id)
    if user_flights:
        flights, page, page_count = paginate_flights(user_flights, 1)
        flights_msg = '\n'.join(flights) or "У вас нет рейсов."
        await message.answer(flights_msg, reply_markup=navigation_markup(page, page_count))
        await Form.viewing_flights.set()
        await Form.main_menu.set()
    else:
        await message.answer("У вас нет зарегистрированных рейсов.")


# Callback для кнопок навигации
@dp.callback_query_handler(lambda call: call.data.startswith('next_') or call.data.startswith('prev_'), state=Form.viewing_flights)
async def navigate_pages(call: types.CallbackQuery, state: FSMContext):
    page = int(call.data.split('_')[1])
    user_flights = get_user_flights(call.from_user.id)
    if call.data.startswith('next_'):
        page += 1
    elif call.data.startswith('prev_'):
        page -= 1
    flights, page, page_count = paginate_flights(user_flights, page)
    if not flights and page > 1:
        page -= 1
        flights, page, page_count = paginate_flights(user_flights, page)
    flights_msg = '\n'.join(flights)
    await call.message.edit_text(flights_msg, reply_markup=navigation_markup(page, page_count))
    await call.answer()



if __name__ == '__main__':
    # Запуск бота
    executor.start_polling(dp, skip_updates=True)
