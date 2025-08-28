# bot.py
import asyncio
import json
import logging
import random
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, PreCheckoutQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
import aiosqlite
import os

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка конфигурации
try:
    with open('config.json', 'r') as f:
        config = json.load(f)
except FileNotFoundError:
    config = {}

BOT_TOKEN = config.get('BOT_TOKEN') or 'YOUR_BOT_TOKEN'
ADMIN_IDS = config.get('ADMIN_IDS', [])
FEE_PERCENT = config.get('FEE_PERCENT', 5)
CURRENCY = "XTR"  # Telegram Stars

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Состояния FSM
class DepositState(StatesGroup):
    waiting_for_amount = State()
    
class CreateGameState(StatesGroup):
    waiting_for_bet = State()
    waiting_for_players = State()

class JoinGameState(StatesGroup):
    waiting_for_deposit = State()

# База данных
DB_NAME = "dice_stars.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                balance INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                creator_id INTEGER,
                joiner_id INTEGER,
                third_player_id INTEGER,
                fourth_player_id INTEGER,
                bet_amount INTEGER,
                creator_dice INTEGER,
                joiner_dice INTEGER,
                third_player_dice INTEGER,
                fourth_player_dice INTEGER,
                winner_id INTEGER,
                status TEXT DEFAULT 'waiting',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                finished_at DATETIME
            )
        ''')
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                status TEXT DEFAULT 'pending',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                type TEXT,
                description TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        await db.commit()

async def get_or_create_user(user_id, username=None, first_name=None, last_name=None):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cursor:
            user = await cursor.fetchone()
            
        if not user:
            await db.execute(
                "INSERT INTO users (id, username, first_name, last_name) VALUES (?, ?, ?, ?)",
                (user_id, username, first_name, last_name)
            )
            await db.commit()
            
            # Создаем начальную запись с нулевыми значениями
            async with db.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cursor:
                user = await cursor.fetchone()
                
        return user

async def update_user_balance(user_id, amount):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE users SET balance = balance + ? WHERE id = ?",
            (amount, user_id)
        )
        await db.commit()

async def add_transaction(user_id, amount, type, description):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO transactions (user_id, amount, type, description) VALUES (?, ?, ?, ?)",
            (user_id, amount, type, description)
        )
        await db.commit()

async def create_game(creator_id, bet_amount, players_count):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "INSERT INTO games (creator_id, bet_amount, status, players_count) VALUES (?, ?, 'waiting', ?)",
            (creator_id, bet_amount, players_count)
        )
        game_id = cursor.lastrowid
        await db.commit()
        return game_id

async def get_active_games():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT * FROM games WHERE status = 'waiting'") as cursor:
            games = await cursor.fetchall()
            return games

async def join_game(game_id, joiner_id):
    async with aiosqlite.connect(DB_NAME) as db:
        # Проверяем, есть ли свободные места
        game = await get_game(game_id)
        if not game:
            return False
            
        if game[2] is None:  # joiner_id
            await db.execute(
                "UPDATE games SET joiner_id = ? WHERE id = ?",
                (joiner_id, game_id)
            )
        elif game[3] is None:  # third_player_id
            await db.execute(
                "UPDATE games SET third_player_id = ? WHERE id = ?",
                (joiner_id, game_id)
            )
        elif game[4] is None:  # fourth_player_id
            await db.execute(
                "UPDATE games SET fourth_player_id = ?, status = 'active' WHERE id = ?",
                (joiner_id, game_id)
            )
        else:
            return False
            
        await db.commit()
        return True

async def update_game_result(game_id, dice_results, winner_id):
    async with aiosqlite.connect(DB_NAME) as db:
        creator_dice, joiner_dice, third_dice, fourth_dice = dice_results
        
        await db.execute(
            "UPDATE games SET creator_dice = ?, joiner_dice = ?, third_player_dice = ?, fourth_player_dice = ?, winner_id = ?, status = 'finished', finished_at = CURRENT_TIMESTAMP WHERE id = ?",
            (creator_dice, joiner_dice, third_dice, fourth_dice, winner_id, game_id)
        )
        
        # Обновляем статистику пользователей
        if winner_id:
            await db.execute(
                "UPDATE users SET wins = wins + 1 WHERE id = ?",
                (winner_id,)
            )
            
            # Находим проигравших
            async with db.execute("SELECT creator_id, joiner_id, third_player_id, fourth_player_id FROM games WHERE id = ?", (game_id,)) as cursor:
                game = await cursor.fetchone()
                losers = [player_id for player_id in game[:4] if player_id and player_id != winner_id]
                
            for loser_id in losers:
                await db.execute(
                    "UPDATE users SET losses = losses + 1 WHERE id = ?",
                    (loser_id,)
                )
        
        await db.commit()

async def get_game(game_id):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT * FROM games WHERE id = ?", (game_id,)) as cursor:
            return await cursor.fetchone()

async def cancel_game(game_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE games SET status = 'cancelled', finished_at = CURRENT_TIMESTAMP WHERE id = ?",
            (game_id,)
        )
        await db.commit()

async def get_game_players(game_id):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT creator_id, joiner_id, third_player_id, fourth_player_id FROM games WHERE id = ?", (game_id,)) as cursor:
            game = await cursor.fetchone()
            return [player_id for player_id in game if player_id is not None]

# Клавиатуры
def main_menu_keyboard():
    keyboard = ReplyKeyboardBuilder()
    keyboard.add(types.KeyboardButton(text="🎲 Создать игру"))
    keyboard.add(types.KeyboardButton(text="🔍 Посмотреть лобби"))
    keyboard.add(types.KeyboardButton(text="⭐ Пополнить"))
    keyboard.add(types.KeyboardButton(text="💼 Профиль"))
    keyboard.add(types.KeyboardButton(text="ℹ️ Помощь"))
    return keyboard.as_markup(resize_keyboard=True)

def back_to_main_keyboard():
    keyboard = ReplyKeyboardBuilder()
    keyboard.add(types.KeyboardButton(text="⬅️ Главное меню"))
    return keyboard.as_markup(resize_keyboard=True)

def game_lobby_keyboard(game_id):
    keyboard = ReplyKeyboardBuilder()
    keyboard.add(types.KeyboardButton(text="🔍 Посмотреть лобби"))
    keyboard.add(types.KeyboardButton(text="❌ Покинуть лобби"))
    keyboard.add(types.KeyboardButton(text="⬅️ Главное меню"))
    return keyboard.as_markup(resize_keyboard=True)

def deposit_keyboard():
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="10 ⭐", callback_data="deposit_10"))
    keyboard.add(InlineKeyboardButton(text="50 ⭐", callback_data="deposit_50"))
    keyboard.add(InlineKeyboardButton(text="100 ⭐", callback_data="deposit_100"))
    keyboard.add(InlineKeyboardButton(text="200 ⭐", callback_data="deposit_200"))
    keyboard.add(InlineKeyboardButton(text="500 ⭐", callback_data="deposit_500"))
    keyboard.add(InlineKeyboardButton(text="1000 ⭐", callback_data="deposit_1000"))
    keyboard.add(InlineKeyboardButton(text="Другая сумма", callback_data="deposit_custom"))
    keyboard.add(InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main"))
    return keyboard.as_markup()

async def games_list_keyboard(games):
    keyboard = InlineKeyboardBuilder()
    for game in games:
        user_data = await get_or_create_user(game[1])
        keyboard.add(InlineKeyboardButton(
            text=f"Игра на {game[3]} ⭐ от @{user_data[1] or 'user'}",
            callback_data=f"join_game_{game[0]}"
        ))
    keyboard.add(InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main"))
    return keyboard.as_markup()

def players_count_keyboard():
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="2 игрока", callback_data="players_2"))
    keyboard.add(InlineKeyboardButton(text="3 игрока", callback_data="players_3"))
    keyboard.add(InlineKeyboardButton(text="4 игрока", callback_data="players_4"))
    keyboard.add(InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main"))
    return keyboard.as_markup()

# Обработчики команд
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user = await get_or_create_user(
        message.from_user.id, 
        message.from_user.username,
        message.from_user.first_name,
        message.from_user.last_name
    )
    
    welcome_text = (
        "🎲 Добро пожаловать в Dice Stars Bot!\n\n"
        "Здесь вы можете играть в кости с другими игроками на Telegram Stars.\n\n"
        "💡 Как играть:\n"
        "1. Создайте игру или присоединитесь к существующей\n"
        "2. Сделайте ставку в звездах\n"
        "3. Бросьте кости и узнайте, кто победил!\n"
        "4. Победитель получает банк за вычетом комиссии 5%\n\n"
        "Удачи! 🍀"
    )
    
    await message.answer(welcome_text, reply_markup=main_menu_keyboard())

@dp.message(F.text == "⬅️ Главное меню")
async def back_to_main(message: types.Message):
    user = await get_or_create_user(message.from_user.id)
    await message.answer("Главное меню:", reply_markup=main_menu_keyboard())

@dp.message(F.text == "💼 Профиль")
async def profile(message: types.Message):
    user = await get_or_create_user(message.from_user.id)
    total_games = user[5] + user[6]
    win_rate = user[5] / total_games * 100 if total_games > 0 else 0
    
    profile_text = (
        f"👤 Ваш профиль:\n\n"
        f"💰 Баланс: {user[4]} ⭐\n"
        f"🏆 Побед: {user[5]}\n"
        f"💔 Поражений: {user[6]}\n"
        f"📊 Винрейт: {win_rate:.1f}%\n\n"
        f"Пригласите друзей и получайте бонусы!"
    )
    
    await message.answer(profile_text, reply_markup=main_menu_keyboard())

@dp.message(F.text == "⭐ Пополнить")
async def deposit(message: types.Message):
    await message.answer("Выберите сумму пополнения:", reply_markup=deposit_keyboard())

@dp.callback_query(F.data.startswith("deposit_"))
async def process_deposit(callback: types.CallbackQuery, state: FSMContext):
    amount_str = callback.data.split("_")[1]
    
    if amount_str == "custom":
        await callback.message.answer("Введите сумму пополнения в звездах:")
        await state.set_state(DepositState.waiting_for_amount)
        return
    
    amounts = {
        "10": 10,
        "50": 50,
        "100": 100,
        "200": 200,
        "500": 500,
        "1000": 1000
    }
    
    amount = amounts.get(amount_str, 10)
    await create_invoice(callback.from_user.id, amount, callback.message)

@dp.message(DepositState.waiting_for_amount)
async def process_custom_deposit(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text)
        if amount < 10:
            await message.answer("❌ Минимальная сумма пополнения - 10 звезд. Попробуйте еще раз:")
            return
            
        await create_invoice(message.from_user.id, amount, message)
        await state.clear()
    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректное число:")

async def create_invoice(user_id, amount, message_obj):
    prices = [LabeledPrice(label=f"Пополнение баланса на {amount} ⭐", amount=amount * 100)]
    
    await message_obj.bot.send_invoice(
        chat_id=user_id,
        title="Пополнение баланса",
        description=f"Пополнение баланса на {amount} Telegram Stars",
        provider_token="",  # Для Stars provider_token должен быть пустой строкой
        currency=CURRENCY,
        prices=prices,
        start_parameter="stars_deposit",
        payload=f"deposit_{amount}_{user_id}"
    )

@dp.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.successful_payment)
async def successful_payment(message: types.Message):
    payload = message.successful_payment.invoice_payload
    parts = payload.split("_")
    
    if len(parts) >= 3 and parts[0] == "deposit":
        amount = int(parts[1])
        user_id = int(parts[2])
        
        await update_user_balance(user_id, amount)
        await add_transaction(user_id, amount, "deposit", "Пополнение через Telegram Stars")
        
        user = await get_or_create_user(user_id)
        await message.answer(f"✅ Ваш баланс пополнен на {amount} ⭐\nТеперь ваш баланс: {user[4]} ⭐", reply_markup=main_menu_keyboard())

@dp.message(F.text == "🎲 Создать игру")
async def create_game_handler(message: types.Message, state: FSMContext):
    user = await get_or_create_user(message.from_user.id)
    
    if user[4] <= 0:
        await message.answer(
            "❌ У вас недостаточно звезд для создания игры.\nПополните баланс сначала.",
            reply_markup=main_menu_keyboard()
        )
        return
    
    await message.answer(
        "Выберите количество игроков:",
        reply_markup=players_count_keyboard()
    )
    await state.set_state(CreateGameState.waiting_for_players)

@dp.callback_query(F.data.startswith("players_"))
async def process_players_count(callback: types.CallbackQuery, state: FSMContext):
    players_count = int(callback.data.split("_")[1])
    await state.update_data(players_count=players_count)
    
    await callback.message.answer(
        "Введите сумму ставки в звездах:",
        reply_markup=back_to_main_keyboard()
    )
    await state.set_state(CreateGameState.waiting_for_bet)

@dp.message(CreateGameState.waiting_for_bet)
async def process_bet_amount(message: types.Message, state: FSMContext):
    try:
        bet_amount = int(message.text)
        user_data = await state.get_data()
        players_count = user_data.get('players_count', 2)
        user = await get_or_create_user(message.from_user.id)
        
        if bet_amount <= 0:
            await message.answer("❌ Ставка должна быть положительным числом. Попробуйте еще раз:")
            return
            
        if user[4] < bet_amount:
            await message.answer(
                f"❌ У вас недостаточно звезд для этой ставки.\nВаш баланс: {user[4]} ⭐",
                reply_markup=main_menu_keyboard()
            )
            await state.clear()
            return
        
        # Замораживаем ставку
        await update_user_balance(message.from_user.id, -bet_amount)
        await add_transaction(message.from_user.id, -bet_amount, "bet", "Создание игры")
        
        # Создаем игру
        game_id = await create_game(message.from_user.id, bet_amount, players_count)
        
        await message.answer(
            f"🎲 Игра создана! Ставка: {bet_amount} ⭐, Игроков: {players_count}\nОжидаем других игроков...",
            reply_markup=game_lobby_keyboard(game_id)
        )
        await state.clear()
    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректное число:")

@dp.message(F.text == "🔍 Посмотреть лобби")
async def find_game(message: types.Message):
    games = await get_active_games()
    
    if not games:
        await message.answer(
            "❌ В настоящее время нет активных игр.\nСоздайте свою или проверьте позже.",
            reply_markup=main_menu_keyboard()
        )
        return
    
    keyboard = await games_list_keyboard(games)
    await message.answer(
        "Выберите игру для присоединения:",
        reply_markup=keyboard
    )

@dp.callback_query(F.data.startswith("join_game_"))
async def join_game_handler(callback: types.CallbackQuery, state: FSMContext):
    game_id = int(callback.data.split("_")[2])
    game = await get_game(game_id)
    
    if not game or game[12] != "waiting":  # status field
        await callback.answer("❌ Эта игра больше не доступна.")
        return
    
    user = await get_or_create_user(callback.from_user.id)
    
    if user[4] < game[3]:  # bet_amount field
        missing_amount = game[3] - user[4]
        await callback.message.answer(
            f"❌ У вас недостаточно звезд для присоединения к этой игре.\nНеобходимо еще: {missing_amount} ⭐",
            reply_markup=deposit_keyboard()
        )
        await state.update_data(game_id=game_id, required_amount=missing_amount)
        await state.set_state(JoinGameState.waiting_for_deposit)
        return
    
    # Замораживаем ставку
    await update_user_balance(callback.from_user.id, -game[3])
    await add_transaction(callback.from_user.id, -game[3], "bet", f"Ставка в игре #{game_id}")
    
    # Присоединяемся к игре
    success = await join_game(game_id, callback.from_user.id)
    
    if not success:
        await callback.message.answer("❌ В игре нет свободных мест.")
        return
    
    # Проверяем, заполнена ли комната
    game = await get_game(game_id)
    players = await get_game_players(game_id)
    
    if len(players) == game[13]:  # players_count field
        # Все игроки на месте, начинаем игру
        await start_game(game_id)
    else:
        await callback.message.answer(
            f"✅ Вы присоединились к игре! Ожидаем остальных игроков... ({len(players)}/{game[13]})",
            reply_markup=main_menu_keyboard()
        )

@dp.message(JoinGameState.waiting_for_deposit)
async def process_join_deposit(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    game_id = user_data.get('game_id')
    required_amount = user_data.get('required_amount')
    
    try:
        amount = int(message.text)
        if amount < required_amount:
            await message.answer(f"❌ Необходимо пополнить минимум на {required_amount} ⭐")
            return
            
        await create_invoice(message.from_user.id, amount, message)
        await state.clear()
        
    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректное число:")

async def start_game(game_id):
    game = await get_game(game_id)
    if not game:
        return
    
    players = await get_game_players(game_id)
    bet_amount = game[3]  # bet_amount field
    
    # Бросаем кости для всех игроков
    dice_results = []
    for player_id in players:
        dice_value = random.randint(1, 6)
        dice_results.append(dice_value)
    
    # Добавляем нули для отсутствующих игроков
    while len(dice_results) < 4:
        dice_results.append(0)
    
    # Определяем победителя
    max_dice = max(dice_results)
    winners = [i for i, dice in enumerate(dice_results) if dice == max_dice]
    
    if len(winners) > 1:
        # Ничья - возвращаем ставки
        for player_id in players:
            await update_user_balance(player_id, bet_amount)
            await add_transaction(player_id, bet_amount, "refund", f"Возврат ставки после ничьи в игре #{game_id}")
        
        winner_id = None
    else:
        # Есть победитель
        winner_index = winners[0]
        winner_id = players[winner_index]
        
        # Вычисляем выигрыш (общий банк минус комиссия)
        total_bank = bet_amount * len(players)
        win_amount = total_bank * (100 - FEE_PERCENT) // 100
        
        # Начисляем выигрыш
        await update_user_balance(winner_id, win_amount)
        await add_transaction(winner_id, win_amount, "win", f"Выигрыш в игре #{game_id}")
    
    # Обновляем результат игры
    await update_game_result(game_id, dice_results, winner_id)
    
    # Отправляем результаты всем игрокам
    result_text = create_result_text(game_id, players, dice_results, winner_id)
    
    for player_id in players:
        try:
            await bot.send_message(player_id, result_text, reply_markup=main_menu_keyboard())
        except Exception as e:
            logger.error(f"Не удалось отправить результат игроку {player_id}: {e}")

def create_result_text(game_id, players, dice_results, winner_id):
    result_text = f"🎯 Игра #{game_id} завершена!\n\n"
    
    for i, player_id in enumerate(players):
        result_text += f"Игрок {i+1}: {dice_results[i]} 🎲\n"
    
    result_text += "\n"
    
    if winner_id is None:
        result_text += "⚔️ Ничья! Ставки возвращены."
    else:
        winner_index = players.index(winner_id) + 1
        result_text += f"🏆 Победитель: Игрок {winner_index}!\n"
        result_text += f"💰 Выигрыш: {dice_results[winner_index-1]} ⭐"
    
    return result_text

@dp.message(F.text == "❌ Покинуть лобби")
async def leave_lobby(message: types.Message):
    # Находим активную игру пользователя
    user_id = message.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT * FROM games WHERE creator_id = ? AND status = 'waiting'", (user_id,)) as cursor:
            game = await cursor.fetchone()
    
    if game:
        # Возвращаем ставку
        await update_user_balance(user_id, game[3])
        await add_transaction(user_id, game[3], "refund", f"Возврат ставки после выхода из лобби #{game[0]}")
        
        # Отменяем игру
        await cancel_game(game[0])
        
        await message.answer(
            "❌ Вы покинули лобби. Ваша ставка возвращена.",
            reply_markup=main_menu_keyboard()
        )
    else:
        await message.answer(
            "❌ У вас нет активных игр.",
            reply_markup=main_menu_keyboard()
        )

@dp.message(F.text == "ℹ️ Помощь")
async def help_command(message: types.Message):
    help_text = (
        "❓ Помощь по боту Dice Stars\n\n"
        "🎲 Как играть:\n"
        "1. Нажмите 'Создать игру' и выберите количество игроков\n"
        "2. Введите сумму ставки\n"
        "3. Дождитесь, пока другие игроки присоединятся к вашей игре\n"
        "4. Или нажмите 'Посмотреть лобби' чтобы присоединиться к существующей\n"
        "5. Бот автоматически бросит кости и определит победителя\n"
        "6. Победитель получает банк за вычетом комиссии 5%\n\n"
        "💸 Пополнение баланса:\n"
        "Нажмите 'Пополнить' и выберите сумму пополнения\n"
        "Оплата осуществляется через Telegram Stars\n\n"
        "📊 В вашем профиле вы можете посмотреть:\n"
        "- Текущий баланс\n"
        "- Статистику побед и поражений\n"
        "- Винрейт\n\n"
        "Если у вас возникли проблемы, обратитесь к администратору."
    )
    
    await message.answer(help_text, reply_markup=main_menu_keyboard())

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())