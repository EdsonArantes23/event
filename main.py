import asyncio
import time
import os
import aiohttp
from typing import Dict, Optional
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import logging

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
                        
                        points = player.get('ggp', 0)
                        
                        auction_result = item.get('currentAuctionResult', {})
                        game_title = auction_result.get('title', '')
                        game_type = auction_result.get('type', '')
                        game_reward = auction_result.get('ggpReward', 0)
                        game_penalty = auction_result.get('ggpPenalty', 0)
                        
                        required_action = item.get('requiredAction', {})
                        action_kind = required_action.get('kind', '')
                        
                        is_active = action_kind == 'content-in-progress'
                        
                        participants[name] = {
                            'points': points,
                            'selected': is_active,
                            'game_title': game_title,
                            'game_type': game_type,
                            'game_reward': game_reward,
                            'game_penalty': game_penalty,
                            'action_kind': action_kind,
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
    
    def _get_leaderboard(self, data: Dict) -> list:
        """Возвращает список участников, отсортированный по очкам (по убыванию)"""
        return sorted(
            data.items(),
            key=lambda x: x[1]['points'],
            reverse=True
        )
    
    def _get_real_position(self, data: Dict, streamer_name: str) -> int:
        """Получает реальную позицию стримера в топе по очкам"""
        leaderboard = self._get_leaderboard(data)
        for i, (name, _) in enumerate(leaderboard, 1):
            if name == streamer_name:
                return i
        return 0
    
    async def get_detailed_streamer_info(self, streamer_name: str) -> Optional[str]:
        """Получает подробную информацию о стримере"""
        try:
            if streamer_name not in STREAMERS.values():
                return None
            
            data = await self.get_participants_data()
            
            if streamer_name not in data:
                return None
            
            info = data[streamer_name]
            real_position = self._get_real_position(data, streamer_name)
            
            message = f"👤 <b>{streamer_name}</b>\n"
            message += f"🏆 <b>Место в топе:</b> {real_position} из {len(data)}\n"
            message += f"⭐ <b>Очки:</b> {info['points']}\n"
            
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
                message += f"\n <b>Статус:</b> Не активен"
            
            return message
            
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return None
    
    async def send_notification(self, message: str):
        try:
            await self.bot.send_message(chat_id=self.chat_id, text=message, parse_mode="HTML")
        except Exception as e:
            logger.error(f" Ошибка отправки: {e}")
    
    async def start(self):
        @self.dp.message(Command("start"))
        async def cmd_start(message: types.Message):
            await message.answer(
                " <b>Бот мониторинга Nassal.pro</b>\n\n"
                "📋 <b>Команды:</b>\n"
                "/top - 🏆 топ лидеров по очкам\n"
                "/points - 📊 таблица всех участников\n"
                "/streamer [номер/имя] - 👤 инфо о стримере\n"
                "/list - список участников\n"
                "/monitor - 🔔 мониторинг изменений\n"
                "/stop - остановить бота",
                reply_markup=self.get_streamer_keyboard()
            )
        
        @self.dp.message(Command("list"))
        async def cmd_list(message: types.Message):
            text = "📋 <b>Список участников:</b>\n\n"
            for num, name in STREAMERS.items():
                text += f"{num}. {name}\n"
            await message.answer(text)
        
        @self.dp.message(Command("top"))
        async def cmd_top(message: types.Message):
            await message.answer("🔄 Получаю топ...")
            data = await self.get_participants_data()
            
            if not data:
                await message.answer(" Не удалось получить данные")
                return
            
            leaderboard = self._get_leaderboard(data)
            
            text = "🏆 <b>Топ лидеров по очкам:</b>\n\n"
            
            medals = {1: "🥇", 2: "🥈", 3: "🥉"}
            
            for i, (name, info) in enumerate(leaderboard, 1):
                points = info['points']
                medal = medals.get(i, f"{i}.")
                marker = "" if info.get('selected') else ""
                
                if points > 0:
                    points_str = f"+{points}"
                else:
                    points_str = str(points)
                
                text += f"{medal} {marker}{name} — <b>{points_str}</b>\n"
            
            await message.answer(text, parse_mode="HTML")
        
        @self.dp.message(Command("points"))
        async def cmd_points(message: types.Message):
            await message.answer("🔄 Получаю очки...")
            data = await self.get_participants_data()
            
            if not data:
                await message.answer("❌ Не удалось получить данные")
                return
            
            text = "📊 <b>Таблица очков:</b>\n\n"
            
            leaderboard = self._get_leaderboard(data)
            
            for i, (name, info) in enumerate(leaderboard, 1):
                points = info['points']
                selected = info.get('selected', False)
                
                if points > 0:
                    emoji = "🟢"
                elif points < 0:
                    emoji = "🔴"
                else:
                    emoji = "⚪"
                
                marker = "🔥" if selected else ""
                text += f"{i}. {marker} {name} - {emoji} <b>{points}</b>\n"
            
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
        
        @self.dp.message(Command("monitor"))
        async def cmd_monitor(message: types.Message):
            await message.answer(" Мониторинг активирован!\n\nБуду присылать:\n• Изменения в очках\n• Смену игр у стримеров")
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
                    await message.answer(f" Загрузка...")
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
        
        # Инициализация — запоминаем текущее состояние без отправки
        initial_data = await self.get_participants_data()
        if initial_data:
            self.previous_data = initial_data
            logger.info(f"✅ Начальное состояние запомнено ({len(initial_data)} участников)")
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
                        await self.send_notification(notification)
                        logger.info(f"📤 Отправлено уведомлений: {len(changes)}")
                
                self.previous_data = current_data
                
            except Exception as e:
                logger.error(f"❌ Ошибка в цикле: {e}")
            
            await asyncio.sleep(10)
    
    def compare_data(self, old_data: Dict, new_data: Dict) -> list:
        """Сравнивает данные и находит изменения"""
        changes = []
        
        # 1. Изменения очков
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
        
        # 2. Смена игр у стримеров
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
