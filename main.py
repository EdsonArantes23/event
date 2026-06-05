import asyncio
import time
import os
import json
import aiohttp
from typing import Dict, Optional, List
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

GROUPS_FILE = "monitoring_groups.json"

ADMINS = [417850992]

class NassalMonitor:
    def __init__(self, bot_token: str):
        self.bot = Bot(token=bot_token)
        self.dp = Dispatcher()
        self.previous_data: Dict = {}
        self.session: Optional[aiohttp.ClientSession] = None
        self.monitoring_groups: List[Dict] = self.load_groups()
    
    def load_groups(self) -> List[Dict]:
        try:
            if os.path.exists(GROUPS_FILE):
                with open(GROUPS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки групп: {e}")
        return []
    
    def save_groups(self):
        try:
            with open(GROUPS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.monitoring_groups, f, ensure_ascii=False, indent=2)
            logger.info(f"💾 Сохранено групп: {len(self.monitoring_groups)}")
        except Exception as e:
            logger.error(f"Ошибка сохранения групп: {e}")
    
    def is_admin(self, user_id: int) -> bool:
        return user_id in ADMINS
    
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
        return sorted(data.items(), key=lambda x: x[1]['points'], reverse=True)
    
    def _get_real_position(self, data: Dict, streamer_name: str) -> int:
        leaderboard = self._get_leaderboard(data)
        for i, (name, _) in enumerate(leaderboard, 1):
            if name == streamer_name:
                return i
        return 0
    
    async def get_detailed_streamer_info(self, streamer_name: str) -> Optional[str]:
        try:
            if streamer_name not in STREAMERS.values():
                return None
            
            data = await self.get_participants_data()
            
            if streamer_name not in data:
                return None
            
            info = data[streamer_name]
            real_position = self._get_real_position(data, streamer_name)
            
            message = f"👤 <b>{streamer_name}</b>\n"
            message += f" <b>Место в топе:</b> {real_position} из {len(data)}\n"
            message += f"⭐ <b>Очки:</b> {info['points']}\n"
            
            if info.get('selected') and info.get('game_title'):
                game_title = info['game_title']
                game_type = info.get('game_type', '')
                game_reward = info.get('game_reward', 0)
                game_penalty = info.get('game_penalty', 0)
                
                if game_type == 'game':
                    message += f"\n <b>Игра:</b> {game_title}"
                else:
                    message += f"\n⚡ <b>Действие:</b> {game_title}"
                
                if game_reward:
                    message += f"\n💰 Награда: +{game_reward}"
                if game_penalty:
                    message += f"\n💔 Штраф: -{game_penalty}"
            else:
                message += f"\n⚪ <b>Статус:</b> Не активен"
            
            return message
            
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return None
    
    async def send_notification(self, message: str):
        if not self.monitoring_groups:
            logger.warning("⚠️ Нет групп для отправки уведомлений")
            return
        
        for group in self.monitoring_groups:
            try:
                chat_id = group['chat_id']
                thread_id = group.get('thread_id')
                
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode="HTML",
                    message_thread_id=thread_id
                )
                logger.info(f"📤 Отправлено в {chat_id}" + (f" (thread: {thread_id})" if thread_id else ""))
            except Exception as e:
                logger.error(f" Ошибка отправки в {group}: {e}")
    
    async def start(self):
        @self.dp.message(Command("add_group"))
        async def cmd_add_group(message: types.Message):
            if not self.is_admin(message.from_user.id):
                await message.answer("❌ Эта команда только для администраторов")
                return
            
            chat_id = message.chat.id
            thread_id = message.message_thread_id
            
            for group in self.monitoring_groups:
                if group['chat_id'] == chat_id and group.get('thread_id') == thread_id:
                    await message.answer("️ Эта группа/ветка уже добавлена в мониторинг")
                    return
            
            group_info = {
                'chat_id': chat_id,
                'chat_title': message.chat.title or 'Unknown',
                'thread_id': thread_id,
                'added_at': time.time()
            }
            
            self.monitoring_groups.append(group_info)
            self.save_groups()
            
            thread_info = f"\n📌 Ветка ID: {thread_id}" if thread_id else ""
            await message.answer(
                f"✅ <b>Группа добавлена в мониторинг!</b>\n\n"
                f" <b>Группа:</b> {message.chat.title}\n"
                f"🆔 <b>Chat ID:</b> {chat_id}"
                f"{thread_info}\n\n"
                f"Теперь сюда будут приходить уведомления об изменениях."
            )
        
        @self.dp.message(Command("remove_group"))
        async def cmd_remove_group(message: types.Message):
            if not self.is_admin(message.from_user.id):
                await message.answer("❌ Эта команда только для администраторов")
                return
            
            chat_id = message.chat.id
            thread_id = message.message_thread_id
            
            self.monitoring_groups = [
                g for g in self.monitoring_groups 
                if not (g['chat_id'] == chat_id and g.get('thread_id') == thread_id)
            ]
            
            self.save_groups()
            
            await message.answer("✅ Группа удалена из мониторинга")
        
        @self.dp.message(Command("list_groups"))
        async def cmd_list_groups(message: types.Message):
            if not self.is_admin(message.from_user.id):
                await message.answer("❌ Эта команда только для администраторов")
                return
            
            if not self.monitoring_groups:
                await message.answer("📋 Список групп мониторинга пуст")
                return
            
            text = "📋 <b>Группы мониторинга:</b>\n\n"
            for i, group in enumerate(self.monitoring_groups, 1):
                thread_info = f" (ветка #{group['thread_id']})" if group.get('thread_id') else ""
                text += f"{i}. <b>{group['chat_title']}</b>{thread_info}\n"
                text += f"   🆔 ID: {group['chat_id']}\n\n"
            
            await message.answer(text, parse_mode="HTML")
        
        @self.dp.message(Command("test_notify"))
        async def cmd_test_notify(message: types.Message):
            if not self.is_admin(message.from_user.id):
                await message.answer("❌ Эта команда только для администраторов")
                return
            
            await message.answer("📤 Отправляю тестовое уведомление...")
            
            test_message = (
                "🔔 <b>Тестовое уведомление</b>\n\n"
                "Это тестовое сообщение для проверки работы мониторинга.\n\n"
                "✅ Если вы видите это сообщение — всё работает!"
            )
            await self.send_notification(test_message)
            
            await message.answer("✅ Тестовое уведомление отправлено")
        
        @self.dp.message(Command("start"))
        async def cmd_start(message: types.Message):
            admin_text = ""
            if self.is_admin(message.from_user.id):
                admin_text = (
                    "\n🔐 <b>Админ команды:</b>\n"
                    "/add_group ➕ добавить эту группу в мониторинг\n"
                    "/remove_group ➖ удалить из мониторинга\n"
                    "/list_groups 📋 список групп\n"
                    "/test_notify  тестовое уведомление\n"
                )
            
            await message.answer(
                "🤖 <b>Бот мониторинга Nassal.pro</b>\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "📋 <b>Доступные команды:</b>\n\n"
                "/top 🏆 топ лидеров по очкам\n"
                "/points 📊 таблица всех участников\n"
                "/streamer [номер/имя] 👤 инфо о стримере\n"
                "/list 📝 список участников\n"
                "/monitor 🔔 включить мониторинг в этой группе"
                + admin_text,
                reply_markup=self.get_streamer_keyboard()
            )
        
        @self.dp.message(Command("list"))
        async def cmd_list(message: types.Message):
            text = "📋 <b>Список участников:</b>\n\n"
            for num, name in STREAMERS.items():
                text += f"{num}. <b>{name}</b>\n"
            await message.answer(text, parse_mode="HTML")
        
        @self.dp.message(Command("top"))
        async def cmd_top(message: types.Message):
            await message.answer("🔄 Получаю топ...")
            data = await self.get_participants_data()
            
            if not data:
                await message.answer("❌ Не удалось получить данные")
                return
            
            leaderboard = self._get_leaderboard(data)
            
            text = "🏆 <b>ТОП ЛИДЕРОВ ПО ОЧКАМ</b>\n"
            text += "━━━━━━━━━━━━━━━━━━━━\n\n"
            
            medals = {1: "", 2: "🥈", 3: "🥉"}
            
            for i, (name, info) in enumerate(leaderboard, 1):
                points = info['points']
                medal = medals.get(i, f"{i}.")
                marker = "🔥" if info.get('selected') else ""
                
                if points > 0:
                    points_str = f"+{points}"
                    points_emoji = "🟢"
                elif points < 0:
                    points_str = str(points)
                    points_emoji = "🔴"
                else:
                    points_str = "0"
                    points_emoji = "⚪"
                
                # Красивое форматирование
                if i <= 3:
                    text += f"{medal} <b>{marker}{name}</b> — {points_emoji} <b>{points_str}</b>\n"
                else:
                    text += f"{i}. {marker}{name} — {points_emoji} <b>{points_str}</b>\n"
            
            text += "\n━━━━━━━━━━━━━━━━━━━━\n"
            text += f"👥 Всего участников: {len(data)}"
            
            await message.answer(text, parse_mode="HTML")
        
        @self.dp.message(Command("points"))
        async def cmd_points(message: types.Message):
            await message.answer("🔄 Получаю очки...")
            data = await self.get_participants_data()
            
            if not data:
                await message.answer("❌ Не удалось получить данные")
                return
            
            text = "📊 <b>ТАБЛИЦА ОЧКОВ</b>\n"
            text += "━━━━━━━━━━━━━━━━━━━━\n\n"
            
            leaderboard = self._get_leaderboard(data)
            
            for i, (name, info) in enumerate(leaderboard, 1):
                points = info['points']
                selected = info.get('selected', False)
                
                if points > 0:
                    emoji = "🟢"
                    points_str = f"+{points}"
                elif points < 0:
                    emoji = ""
                    points_str = str(points)
                else:
                    emoji = "⚪"
                    points_str = "0"
                
                marker = "🔥" if selected else ""
                text += f"{i}. {marker} <b>{name}</b> — {emoji} <b>{points_str}</b>\n"
            
            text += "\n━━━━━━━━━━━━━━━━━━━━\n"
            text += "🔥 — сейчас активен"
            
            await message.answer(text, parse_mode="HTML")
        
        @self.dp.message(Command("streamer"))
        async def cmd_streamer(message: types.Message):
            if len(message.text.split()) < 2:
                await message.answer(" Укажите номер или имя\nПример: /streamer 1")
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
            
            await message.answer(f"⏳ Загрузка информации о <b>{streamer_name}</b>...", parse_mode="HTML")
            info = await self.get_detailed_streamer_info(streamer_name)
            
            if info:
                await message.answer(info, parse_mode="HTML")
            else:
                await message.answer(f"❌ Не удалось получить информацию о {streamer_name}")
        
        @self.dp.message(Command("monitor"))
        async def cmd_monitor(message: types.Message):
            chat_id = message.chat.id
            thread_id = message.message_thread_id
            
            for group in self.monitoring_groups:
                if group['chat_id'] == chat_id and group.get('thread_id') == thread_id:
                    await message.answer("✅ Мониторинг уже активен в этой группе/ветке!")
                    return
            
            group_info = {
                'chat_id': chat_id,
                'chat_title': message.chat.title or 'Unknown',
                'thread_id': thread_id,
                'added_at': time.time()
            }
            
            self.monitoring_groups.append(group_info)
            self.save_groups()
            
            thread_info = f"\n📌 <b>Ветка ID:</b> {thread_id}" if thread_id else ""
            await message.answer(
                f"🔔 <b>Мониторинг активирован!</b>\n\n"
                f"Буду присылать сюда уведомления о:\n"
                f"•  Изменениях в очках\n"
                f"• 🎮 Смене игр у стримеров\n"
                f"• 📊 Изменениях позиций в топе"
                f"{thread_info}",
                parse_mode="HTML"
            )
            
            if not self.previous_data:
                asyncio.create_task(self.monitor_loop())
        
        @self.dp.message(Command("stop"))
        async def cmd_stop(message: types.Message):
            if not self.is_admin(message.from_user.id):
                await message.answer("❌ Эта команда только для администраторов")
                return
            
            await message.answer("👋 Бот остановлен")
            if self.session:
                await self.session.close()
            await self.bot.close()
        
        @self.dp.message()
        async def handle_keyboard(message: types.Message):
            text = message.text.strip()
            for num, name in STREAMERS.items():
                if text == f"{num}. {name}" or text == name:
                    await message.answer(f"⏳ Загрузка информации о <b>{name}</b>...", parse_mode="HTML")
                    info = await self.get_detailed_streamer_info(name)
                    if info:
                        await message.answer(info, parse_mode="HTML")
                    else:
                        await message.answer(f" Не удалось получить информацию о {name}")
                    return
        
        logger.info("🚀 Бот запущен!")
        logger.info(f"👥 Админы: {ADMINS}")
        logger.info(f"📋 Групп мониторинга: {len(self.monitoring_groups)}")
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
                        notification = self._format_notification(changes)
                        await self.send_notification(notification)
                        logger.info(f"📤 Отправлено уведомлений")
                
                self.previous_data = current_data
                
            except Exception as e:
                logger.error(f"❌ Ошибка в цикле: {e}")
            
            await asyncio.sleep(10)
    
    def _format_notification(self, changes: list) -> str:
        """Красиво форматирует уведомление"""
        notification = "🔔 <b>ИЗМЕНЕНИЯ НА NASSAL.PRO</b>\n"
        notification += "━━━━━━━━━━━━━━━━━━━━\n\n"
        notification += "\n".join(changes)
        notification += "\n\n━━━━━━━━━━━━━━━━━━━━"
        return notification
    
    def compare_data(self, old_data: Dict, new_data: Dict) -> list:
        changes = []
        
        # Получаем старые и новые позиции
        old_positions = {}
        new_positions = {}
        
        old_leaderboard = self._get_leaderboard(old_data)
        new_leaderboard = self._get_leaderboard(new_data)
        
        for i, (name, _) in enumerate(old_leaderboard, 1):
            old_positions[name] = i
        
        for i, (name, _) in enumerate(new_leaderboard, 1):
            new_positions[name] = i
        
        # 1. Изменения позиций
        position_changes = []
        for name in new_data.keys():
            if name in old_positions and name in new_positions:
                old_pos = old_positions[name]
                new_pos = new_positions[name]
                
                if old_pos != new_pos:
                    diff = old_pos - new_pos  # Положительное = поднялся
                    if diff > 0:
                        arrow = "⬆️"
                        direction = "поднялся"
                        emoji = ""
                    else:
                        arrow = "️"
                        direction = "упал"
                        emoji = "📉"
                        diff = abs(diff)
                    
                    position_changes.append(
                        f"{emoji} <b>{name}</b> {direction} на {diff} {self._get_position_word(diff)}!\n"
                        f"{arrow} Было: {old_pos} место → Стало: {new_pos} место"
                    )
        
        if position_changes:
            changes.append("📊 <b>ИЗМЕНЕНИЯ В ПОЗИЦИЯХ:</b>\n\n" + "\n\n".join(position_changes))
        
        # 2. Изменения очков
        points_changes = []
        for name, data in new_data.items():
            if name in old_data:
                old_points = old_data[name].get('points', 0)
                new_points = data.get('points', 0)
                
                if old_points != new_points:
                    diff = new_points - old_points
                    if diff > 0:
                        arrow = "⬆️"
                        emoji = "💚"
                        sign = "+"
                    else:
                        arrow = "⬇️"
                        emoji = "💔"
                        sign = ""
                    
                    points_changes.append(
                        f"{emoji} <b>{name}</b>\n"
                        f"{arrow} Очки: {old_points} → {new_points} ({sign}{diff})"
                    )
        
        if points_changes:
            changes.append("💰 <b>ИЗМЕНЕНИЯ В ОЧКАХ:</b>\n\n" + "\n\n".join(points_changes))
        
        # 3. Смена игр
        game_changes = []
        for name, data in new_data.items():
            if name in old_data:
                old_game = old_data[name].get('game_title', '')
                new_game = data.get('game_title', '')
                
                if old_game != new_game and new_game:
                    game_changes.append(
                        f"🎮 <b>{name}</b>\n"
                        f"❌ Было: {old_game or 'Нет'}\n"
                        f"✅ Стало: {new_game}"
                    )
        
        if game_changes:
            changes.append("🎮 <b>СМЕНА ИГР:</b>\n\n" + "\n\n".join(game_changes))
        
        return changes
    
    def _get_position_word(self, count: int) -> str:
        """Склонение слова 'позиция'"""
        if count == 1:
            return "позицию"
        elif 2 <= count <= 4:
            return "позиции"
        else:
            return "позиций"


async def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN не найден!")
        return
    
    logger.info(f"✅ Запуск бота")
    monitor = NassalMonitor(BOT_TOKEN)
    await monitor.start()


if __name__ == "__main__":
    asyncio.run(main())
