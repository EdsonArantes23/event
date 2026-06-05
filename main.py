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

# ПРАВИЛЬНЫЙ URL API
API_URL = "https://api-game.nassal.pro/api/public/player/list"

class NassalMonitor:
    def __init__(self, bot_token: str, chat_id: int):
        self.bot = Bot(token=bot_token)
        self.dp = Dispatcher()
        self.chat_id = chat_id
        self.previous_data: Dict = {}
        self.session: Optional[aiohttp.ClientSession] = None
    
    def get_streamer_keyboard(self) -> ReplyKeyboardMarkup:
        """Создает клавиатуру со списком стримеров"""
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
                logger.info(f"✅ Получено данных: {data.get('data', {}).get('count', 0)} участников")
                
                participants = {}
                
                # Парсим массив участников
                for idx, item in enumerate(data.get('data', {}).get('array', [])):
                    try:
                        player = item.get('player', {})
                        name = player.get('name', f'Unknown_{idx}')
                        
                        # Получаем статус игрока
                        status = player.get('status', '')
                        
                        # Получаем текущее действие
                        required_action = item.get('requiredAction', {})
                        action_kind = required_action.get('kind', '')
                        content_type = required_action.get('contentType', '')
                        
                        # Получаем информацию об аукционе
                        auction_result = item.get('currentAuctionResult', {})
                        
                        # Определяем, активен ли игрок
                        is_active = action_kind == 'content-in-progress' or status == 'content'
                        
                        participants[name] = {
                            'position': idx + 1,
                            'points': '0',  # Очки пока не видны в API
                            'selected': is_active,
                            'status': status,
                            'action_kind': action_kind,
                            'content_type': content_type,
                            'auction_result': auction_result,
                            'timestamp': time.time()
                        }
                        
                    except Exception as e:
                        logger.warning(f"⚠️ Ошибка парсинга участника {idx}: {e}")
                        continue
                
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
            
            # Формируем сообщение
            message = f"👤 <b>{streamer_name}</b>\n"
            message += f"📊 Позиция: {info['position']}\n"
            message += f"⭐ Очки: {info.get('points', '0')}\n"
            message += f"📌 Статус: {info.get('status', 'неизвестно')}\n"
            
            if info.get('selected'):
                action_kind = info.get('action_kind', '')
                content_type = info.get('content_type', '')
                
                if action_kind == 'content-in-progress':
                    if content_type == 'game':
                        message += f"\n🎮 <b>Сейчас играет</b>"
                    else:
                        message += f"\n⚡ <b>Действие:</b> {content_type}"
                else:
                    message += f"\n⚡ <b>Статус:</b> {action_kind or 'активен'}"
            else:
                message += f"\n⚡ <b>Статус:</b> Не активен"
            
            return message
            
        except Exception as e:
            logger.error(f"❌ Ошибка при получении информации о {streamer_name}: {e}")
            return None
    
    async def send_notification(self, message: str):
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"❌ Ошибка отправки сообщения: {e}")
    
    async def start(self):
        @self.dp.message(Command("start"))
        async def cmd_start(message: types.Message):
            await message.answer(
                "🤖 <b>Бот мониторинга Nassal.pro запущен!</b>\n\n"
                "📋 <b>Доступные команды:</b>\n"
                "/status - текущий активный стример\n"
                "/streamer [номер/имя] - информация о стримере\n"
                "/points - очки всех участников\n"
                "/list - список всех участников\n"
                "/monitor - начать мониторинг изменений\n"
                "/stop - остановить бота\n\n"
                "Или выберите стримера из меню:",
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
            await message.answer("🔄 Получаю текущие очки...")
            
            data = await self.get_participants_data()
            
            if not data:
                await message.answer("❌ Не удалось получить данные")
                return
            
            text = "📊 <b>Текущие очки участников:</b>\n\n"
            
            sorted_participants = sorted(
                [(name, info) for name, info in data.items()],
                key=lambda x: x[1]['position']
            )
            
            for name, info in sorted_participants:
                points = info.get('points', '0')
                position = info.get('position', 0)
                selected = info.get('selected', False)
                
                points_int = int(points) if points.lstrip('-').isdigit() else 0
                if points_int > 0:
                    points_emoji = "🟢"
                elif points_int < 0:
                    points_emoji = "🔴"
                else:
                    points_emoji = "⚪"
                
                active_marker = "🔥" if selected else ""
                text += f"{position}. {active_marker} {name} - {points_emoji} <b>{points}</b>\n"
            
            text += f"\n⏰ {datetime.now().strftime('%H:%M:%S')}"
            
            await message.answer(text, parse_mode="HTML")
        
        @self.dp.message(Command("streamer"))
        async def cmd_streamer(message: types.Message):
            if len(message.text.split()) < 2:
                await message.answer(
                    "❌ <b>Укажите номер или имя стримера</b>\n\n"
                    "Примеры:\n"
                    "/streamer 1\n"
                    "/streamer Flashko"
                )
                return
            
            query = message.text.split(maxsplit=1)[1].strip()
            streamer_name = None
            
            if query.isdigit():
                num = int(query)
                if num in STREAMERS:
                    streamer_name = STREAMERS[num]
                else:
                    await message.answer(f"❌ Стример с номером {num} не найден")
                    return
            else:
                query_lower = query.lower()
                if query_lower in STREAMERS_BY_NAME:
                    streamer_name = STREAMERS[STREAMERS_BY_NAME[query_lower]]
                else:
                    found = False
                    for name in STREAMERS.values():
                        if query_lower in name.lower():
                            streamer_name = name
                            found = True
                            break
                    if not found:
                        await message.answer(f"❌ Стример '{query}' не найден")
                        return
            
            await message.answer(f"⏳ Загрузка информации о {streamer_name}...")
            
            info = await self.get_detailed_streamer_info(streamer_name)
            
            if info:
                await message.answer(info, parse_mode="HTML")
            else:
                await message.answer(f"❌ Не удалось получить информацию о {streamer_name}")
        
        @self.dp.message(Command("status"))
        async def cmd_status(message: types.Message):
            await message.answer("🔄 Получаю текущий статус...")
            
            data = await self.get_participants_data()
            
            if not data:
                await message.answer("❌ Не удалось получить данные")
                return
            
            active_streamer = None
            for name, info in data.items():
                if info.get('selected'):
                    active_streamer = name
                    break
            
            text = f"📊 <b>Текущий статус</b>\n\n"
            
            if active_streamer:
                active_points = data[active_streamer].get('points', '0')
                status = data[active_streamer].get('status', 'неизвестно')
                
                text += f"🎯 <b>Активен:</b> {active_streamer}\n"
                text += f"⭐ <b>Очки:</b> {active_points}\n"
                text += f"📌 <b>Статус:</b> {status}\n"
            else:
                text += "⚡ <b>Никто не активен</b>"
            
            text += f"\n\n⏰ {datetime.now().strftime('%H:%M:%S')}"
            
            await message.answer(text, parse_mode="HTML")
        
        @self.dp.message(Command("monitor"))
        async def cmd_monitor(message: types.Message):
            await message.answer("🔔 Мониторинг изменений активирован!\n\nБот будет присылать:\n• Смену активного стримера\n• Изменение статусов\n• Изменения в очках")
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
                    await message.answer(f"⏳ Загрузка информации о {name}...")
                    
                    info = await self.get_detailed_streamer_info(name)
                    
                    if info:
                        await message.answer(info, parse_mode="HTML")
                    else:
                        await message.answer(f"❌ Не удалось получить информацию о {name}")
                    return
        
        logger.info("🚀 Бот запущен!")
        await self.dp.start_polling(self.bot)
    
    async def monitor_loop(self):
        logger.info("Запуск мониторинга...")
        
        # Инициализация
        logger.info("🔄 Инициализация: получаем текущее состояние...")
        initial_data = await self.get_participants_data()
        
        if initial_data:
            self.previous_data = initial_data
            logger.info(f"✅ Начальное состояние запомнено ({len(initial_data)} участников)")
            logger.info("🔍 Теперь буду следить за изменениями...")
        else:
            logger.error("❌ Не удалось получить начальное состояние")
            return
        
        # Основной цикл
        while True:
            try:
                current_data = await self.get_participants_data()
                
                if current_data:
                    if self.previous_data:
                        changes = self.compare_data(self.previous_data, current_data)
                        
                        if changes:
                            notification = "🔔 <b>Изменения на Nassal.pro</b>\n\n"
                            notification += "\n━━━━━━━━━━━━\n".join(changes)
                            notification += f"\n\n⏰ {time.strftime('%H:%M:%S')}"
                            
                            await self.send_notification(notification)
                            logger.info(f"📤 Отправлено уведомлений: {len(changes)}")
                    
                    self.previous_data = current_data
                    
            except Exception as e:
                logger.error(f"❌ Ошибка в цикле мониторинга: {e}")
            
            await asyncio.sleep(10)
    
    def compare_data(self, old_data: Dict, new_data: Dict) -> list:
        """Сравнивает данные и находит изменения"""
        changes = []
        
        # Проверяем смену активного стримера
        old_active = None
        new_active = None
        
        for name, info in old_data.items():
            if info.get('selected'):
                old_active = name
                break
        
        for name, info in new_data.items():
            if info.get('selected'):
                new_active = name
                break
        
        if old_active != new_active:
            if new_active:
                changes.append(f"🔥 <b>{new_active}</b> стал активным!")
            elif old_active:
                changes.append(f"⚡ <b>{old_active}</b> завершил действие")
        
        # Проверяем изменения статусов
        for name, data in new_data.items():
            if name in old_data:
                old_status = old_data[name].get('status', '')
                new_status = data.get('status', '')
                
                if old_status != new_status:
                    changes.append(
                        f"📌 <b>{name}</b>\n"
                        f"❌ Было: {old_status}\n"
                        f"✅ Стало: {new_status}"
                    )
        
        # Проверяем изменения очков
        points_changes = []
        for name, data in new_data.items():
            if name in old_data:
                old_points = old_data[name].get('points', '0')
                new_points = data.get('points', '0')
                
                if old_points != new_points:
                    try:
                        diff = int(new_points) - int(old_points)
                        arrow = "⬆️" if diff > 0 else "⬇️"
                        sign = "+" if diff > 0 else ""
                        points_changes.append(
                            f"{arrow} <b>{name}</b>\n"
                            f"Очки: {old_points} → {new_points} ({sign}{diff})"
                        )
                    except:
                        points_changes.append(
                            f"⭐ <b>{name}</b>\n"
                            f"Очки: {old_points} → {new_points}"
                        )
        
        if points_changes:
            changes.append("💰 <b>Изменения в очках:</b>\n" + "\n".join(points_changes))
        
        return changes


async def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    CHAT_ID = os.getenv("CHAT_ID", "-1003268832776")
    
    if not BOT_TOKEN:
        logger.error("❌ Переменная окружения BOT_TOKEN не найдена!")
        return
    
    try:
        CHAT_ID = int(CHAT_ID)
    except ValueError:
        logger.error(f"❌ CHAT_ID имеет неверный формат: {CHAT_ID}")
        return
    
    logger.info(f"✅ Бот запускается с chat_id: {CHAT_ID}")
    
    monitor = NassalMonitor(BOT_TOKEN, CHAT_ID)
    await monitor.start()


if __name__ == "__main__":
    asyncio.run(main())
