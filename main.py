import asyncio
import time
import os
import aiohttp
from typing import Dict, Optional
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STREAMERS = {
    1: "Dunduk",
    2: "F1ashko",
    3: "GladValakas",
    4: "KarmikKoala",
    5: "Lasqa",
    6: "Maddyson",
    7: "Melharucos",
    8: "Nenormova",
    9: "Praden",
    10: "ViktorZu",
    11: "C_a_k_e",
    12: "Arrowwoods"
}

STREAMERS_BY_NAME = {name.lower(): num for num, name in STREAMERS.items()}

API_URL = "https://api-game.nassal.pro/api/public/player/list"

class NassalMonitor:
    def __init__(self, bot_token: str, chat_id: int):
        self.bot = Bot(token=bot_token)
        self.dp = Dispatcher()
        self.chat_id = chat_id
        self.previous_data: Dict = {}
        self.session: Optional[aiohttp.ClientSession] = None
    
    def get_streamer_keyboard(self) -> ReplyKeyboardMarkup:
        keyboard = []
        row = []
        for num, name in STREAMERS.items():
            row.append(KeyboardButton(text=f"{num}. {name}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
    
    async def get_participants_data(self) -> Dict:
        """Получает данные всех участников через API"""
        try:
            logger.info("🌐 Запрашиваю данные с API...")
            
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            async with self.session.get(API_URL) as response:
                if response.status != 200:
                    logger.error(f"❌ Ошибка API: {response.status}")
                    return {}
                
                data = await response.json()
                participants = {}
                
                for item in data.get('data', {}).get('array', []):
                    try:
                        player = item.get('player', {})
                        name = player.get('name', '')
                        
                        if not name or name not in STREAMERS.values():
                            continue
                        
                        # Очки из player.ggp
                        points = player.get('ggp', 0)
                        
                        # Позиция из нашего словаря
                        position = STREAMERS_BY_NAME.get(name.lower(), 0)
                        
                        # Информация об игре/действии
                        auction_result = item.get('currentAuctionResult', {})
                        game_title = auction_result.get('title', '')
                        game_type = auction_result.get('type', '')
                        game_reward = auction_result.get('ggpReward', 0)
                        game_penalty = auction_result.get('ggpPenalty', 0)
                        game_image = auction_result.get('imageUrl', '')
                        
                        # Статус действия
                        required_action = item.get('requiredAction', {})
                        action_kind = required_action.get('kind', '')
                        content_type = required_action.get('contentType', '')
                        
                        # Активен ли игрок
                        is_active = action_kind == 'content-in-progress'
                        
                        # Время начала (для определения "главного" активного)
                        timer_started = auction_result.get('timerStartedAt', '')
                        
                        participants[name] = {
                            'position': position,
                            'points': points,
                            'selected': is_active,
                            'game_title': game_title,
                            'game_type': game_type,
                            'game_reward': game_reward,
                            'game_penalty': game_penalty,
                            'game_image': game_image,
                            'action_kind': action_kind,
                            'content_type': content_type,
                            'timer_started': timer_started,
                            'timestamp': time.time()
                        }
                        
                    except Exception as e:
                        logger.warning(f"⚠️ Ошибка парсинга: {e}")
                        continue
                
                logger.info(f"✅ Получено {len(participants)} участников")
                return participants
                
        except Exception as e:
            logger.error(f"❌ Ошибка при получении данных: {e}")
            return {}
    
    async def get_detailed_streamer_info(self, streamer_name: str) -> Optional[str]:
        """Получает подробную информацию о стримере"""
        try:
            if streamer_name not in STREAMERS.values():
                return None
            
            data = await self.get_participants_data()
            
            if streamer_name not in data:
                return None
            
            info = data[streamer_name]
            
            message = f"👤 <b>{streamer_name}</b>\n"
            message += f"📊 Позиция: {info['position']}\n"
            message += f"⭐ <b>Очки: {info['points']}</b>\n"
            
            if info.get('selected') and info.get('game_title'):
                game_title = info['game_title']
                game_type = info.get('game_type', '')
                game_reward = info.get('game_reward', 0)
                game_penalty = info.get('game_penalty', 0)
                
                if game_type == 'game':
                    message += f"\n🎮 <b>Игра:</b> {game_title}"
                else:
                    message += f"\n⚡ <b>Действие:</b> {game_title}"
                
                if game_reward:
                    message += f"\n💰 Награда: +{game_reward}"
                if game_penalty:
                    message += f"\n💔 Штраф: -{game_penalty}"
            else:
                message += f"\n⚡ <b>Статус:</b> Не активен"
            
            return message
            
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return None
    
    async def send_notification(self, message: str):
        try:
            await self.bot.send_message(chat_id=self.chat_id, text=message, parse_mode="HTML")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки: {e}")
    
    async def start(self):
        @self.dp.message(Command("start"))
        async def cmd_start(message: types.Message):
            await message.answer(
                "🤖 <b>Бот мониторинга Nassal.pro</b>\n\n"
                "📋 <b>Команды:</b>\n"
                "/status - текущий статус\n"
                "/streamer [номер/имя] - инфо о стримере\n"
                "/points - таблица очков\n"
                "/list - список участников\n"
                "/monitor - мониторинг изменений\n"
                "/stop - остановить бота",
                reply_markup=self.get_streamer_keyboard()
            )
        
        @self.dp.message(Command("list"))
        async def cmd_list(message: types.Message):
            text = "📋 <b>Список участников:</b>\n\n"
            for num, name in STREAMERS.items():
                text += f"{num}. {name}\n"
            await message.answer(text)
        
        @self.dp.message(Command("points"))
        async def cmd_points(message: types.Message):
            await message.answer("🔄 Получаю очки...")
            data = await self.get_participants_data()
            
            if not data:
                await message.answer("❌ Не удалось получить данные")
                return
            
            text = "📊 <b>Таблица очков:</b>\n\n"
            
            # Сортируем по позиции (из нашего словаря)
            sorted_participants = sorted(data.items(), key=lambda x: x[1]['position'])
            
            for name, info in sorted_participants:
                points = info['points']
                position = info['position']
                selected = info.get('selected', False)
                
                if points > 0:
                    emoji = "🟢"
                elif points < 0:
                    emoji = "🔴"
                else:
                    emoji = "⚪"
                
                marker = "🔥" if selected else ""
                text += f"{position}. {marker} {name} - {emoji} <b>{points}</b>\n"
            
            text += f"\n⏰ {datetime.now().strftime('%H:%M:%S')}"
            await message.answer(text, parse_mode="HTML")
        
        @self.dp.message(Command("streamer"))
        async def cmd_streamer(message: types.Message):
            if len(message.text.split()) < 2:
                await message.answer("❌ Укажите номер или имя\nПример: /streamer 1")
                return
            
            query = message.text.split(maxsplit=1)[1].strip()
            streamer_name = None
            
            if query.isdigit():
                num = int(query)
                streamer_name = STREAMERS.get(num)
            else:
                query_lower = query.lower()
                if query_lower in STREAMERS_BY_NAME:
                    streamer_name = STREAMERS[STREAMERS_BY_NAME[query_lower]]
                else:
                    for name in STREAMERS.values():
                        if query_lower in name.lower():
                            streamer_name = name
                            break
            
            if not streamer_name:
                await message.answer(f"❌ Стример '{query}' не найден")
                return
            
            await message.answer(f"⏳ Загрузка...")
            info = await self.get_detailed_streamer_info(streamer_name)
            
            if info:
                await message.answer(info, parse_mode="HTML")
            else:
                await message.answer(f"❌ Не удалось получить информацию")
        
        @self.dp.message(Command("status"))
        async def cmd_status(message: types.Message):
            await message.answer("🔄 Получаю статус...")
            data = await self.get_participants_data()
            
            if not data:
                await message.answer("❌ Не удалось получить данные")
                return
            
            # Находим активного (у кого самый свежий timerStartedAt)
            active_streamer = None
            latest_time = ""
            
            for name, info in data.items():
                if info.get('selected') and info.get('timer_started'):
                    if info['timer_started'] > latest_time:
                        latest_time = info['timer_started']
                        active_streamer = name
            
            text = "📊 <b>Текущий статус</b>\n\n"
            
            if active_streamer:
                info = data[active_streamer]
                game_title = info.get('game_title', 'Неизвестно')
                game_type = info.get('game_type', '')
                
                text += f"🎯 <b>Активен:</b> {active_streamer}\n"
                text += f"⭐ <b>Очки:</b> {info['points']}\n"
                
                if game_type == 'game':
                    text += f"🎮 <b>Игра:</b> {game_title}\n"
                else:
                    text += f"⚡ <b>Действие:</b> {game_title}\n"
            else:
                text += "⚡ <b>Никто не активен</b>"
            
            text += f"\n\n⏰ {datetime.now().strftime('%H:%M:%S')}"
            await message.answer(text, parse_mode="HTML")
        
        @self.dp.message(Command("monitor"))
        async def cmd_monitor(message: types.Message):
            await message.answer("🔔 Мониторинг активирован!")
            asyncio.create_task(self.monitor_loop())
        
        @self.dp.message(Command("stop"))
        async def cmd_stop(message: types.Message):
            await message.answer("👋 Бот остановлен")
            if self.session:
                await self.session.close()
            await self.bot.close()
        
        @self.dp.message()
        async def handle_keyboard(message: types.Message):
            text = message.text.strip()
            for num, name in STREAMERS.items():
                if text == f"{num}. {name}" or text == name:
                    await message.answer(f"⏳ Загрузка...")
                    info = await self.get_detailed_streamer_info(name)
                    if info:
                        await message.answer(info, parse_mode="HTML")
                    else:
                        await message.answer(f"❌ Не удалось получить информацию")
                    return
        
        logger.info("🚀 Бот запущен!")
        await self.dp.start_polling(self.bot)
    
    async def monitor_loop(self):
        logger.info("Запуск мониторинга...")
        
        initial_data = await self.get_participants_data()
        if initial_data:
            self.previous_data = initial_data
            logger.info(f"✅ Начальное состояние запомнено")
        else:
            logger.error("❌ Не удалось получить начальное состояние")
            return
        
        while True:
            try:
                current_data = await self.get_participants_data()
                
                if current_data and self.previous_data:
                    changes = self.compare_data(self.previous_data, current_data)
                    
                    if changes:
                        notification = "🔔 <b>Изменения на Nassal.pro</b>\n\n"
                        notification += "\n━━━━━━━━━━━━\n".join(changes)
                        notification += f"\n\n⏰ {time.strftime('%H:%M:%S')}"
                        await self.send_notification(notification)
                
                self.previous_data = current_data
                
            except Exception as e:
                logger.error(f"❌ Ошибка: {e}")
            
            await asyncio.sleep(10)
    
    def compare_data(self, old_data: Dict, new_data: Dict) -> list:
        changes = []
        
        # Изменения очков
        points_changes = []
        for name, data in new_data.items():
            if name in old_data:
                old_points = old_data[name].get('points', 0)
                new_points = data.get('points', 0)
                
                if old_points != new_points:
                    diff = new_points - old_points
                    arrow = "⬆️" if diff > 0 else "⬇️"
                    sign = "+" if diff > 0 else ""
                    points_changes.append(
                        f"{arrow} <b>{name}</b>\n"
                        f"Очки: {old_points} → {new_points} ({sign}{diff})"
                    )
        
        if points_changes:
            changes.append("💰 <b>Изменения в очках:</b>\n" + "\n".join(points_changes))
        
        # Изменения игр
        for name, data in new_data.items():
            if name in old_data:
                old_game = old_data[name].get('game_title', '')
                new_game = data.get('game_title', '')
                
                if old_game != new_game and new_game:
                    changes.append(
                        f"🎮 <b>{name}</b>\n"
                        f"❌ Было: {old_game or 'Нет'}\n"
                        f"✅ Стало: {new_game}"
                    )
        
        return changes


async def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    CHAT_ID = os.getenv("CHAT_ID", "-1003268832776")
    
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN не найден!")
        return
    
    try:
        CHAT_ID = int(CHAT_ID)
    except ValueError:
        logger.error(f"❌ Неверный CHAT_ID: {CHAT_ID}")
        return
    
    logger.info(f"✅ Запуск с chat_id: {CHAT_ID}")
    monitor = NassalMonitor(BOT_TOKEN, CHAT_ID)
    await monitor.start()


if __name__ == "__main__":
    asyncio.run(main())
