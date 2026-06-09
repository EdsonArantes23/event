import asyncio
import time
import os
import json
import re
import aiohttp
from typing import Dict, Optional, List
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
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

STREAMERS_BY_NAME = {name.lower().strip(): num for num, name in STREAMERS.items()}
VALID_NAMES = {name.lower().strip() for name in STREAMERS.values()}

API_URL = "https://api-game.nassal.pro/api/public/player/list"

GROUPS_FILE = "monitoring_groups.json"

ADMINS = [417850992]

NUMBERS_WORDS = {
    1: "одно", 2: "два", 3: "три", 4: "четыре", 5: "пять",
    6: "шесть", 7: "семь", 8: "восемь", 9: "девять", 10: "десять",
    11: "одиннадцать", 12: "двенадцать", 13: "тринадцать", 14: "четырнадцать",
    15: "пятнадцать", 16: "шестнадцать", 17: "семнадцать", 18: "восемнадцать",
    19: "девятнадцать", 20: "двадцать"
}

class NassalMonitor:
    def __init__(self, bot_token: str):
        self.bot = Bot(token=bot_token)
        self.dp = Dispatcher()
        self.previous_data: Dict = {}
        self.session: Optional[aiohttp.ClientSession] = None
        self.monitoring_groups: List[Dict] = self.load_groups()
        self.monitoring_active: bool = False
        self.player_cache: Dict[str, Dict] = {}
        self.monitor_loop_task: Optional[asyncio.Task] = None
    
    def load_groups(self) -> List[Dict]:
        try:
            if os.path.exists(GROUPS_FILE):
                with open(GROUPS_FILE, 'r', encoding='utf-8') as f:
                    groups = json.load(f)
                logger.info(f"📂 Загружено групп: {len(groups)}")
                return groups
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
    
    def _number_to_word(self, number: int) -> str:
        number = abs(number)
        if number in NUMBERS_WORDS:
            return NUMBERS_WORDS[number]
        return str(number)
    
    def _get_position_word(self, count: int) -> str:
        count = abs(count)
        if count % 10 == 1 and count % 100 != 11:
            return "место"
        elif count % 10 in [2, 3, 4] and count % 100 not in [12, 13, 14]:
            return "места"
        else:
            return "мест"
    
    def _visible_len(self, text: str) -> int:
        clean = re.sub(r'<[^>]+>', '', text)
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"
            "\U0001F300-\U0001F5FF"
            "\U0001F680-\U0001F6FF"
            "\U0001F1E0-\U0001F1FF"
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "\U0001f926-\U0001f937"
            "\U00010000-\U0010ffff"
            "\u2640-\u2642"
            "\u2600-\u2B55"
            "\u200d"
            "\u23cf"
            "\u23e9"
            "\u231a"
            "\ufe0f"
            "\u3030"
            "]+", flags=re.UNICODE)
        clean = emoji_pattern.sub('', clean)
        return len(clean)
    
    def _format_time_duration(self, seconds: int) -> str:
        """Форматирует секунды в читаемый формат"""
        if seconds < 0:
            seconds = 0
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        if hours > 0:
            return f"{hours} ч {minutes} мин {secs} сек"
        elif minutes > 0:
            return f"{minutes} мин {secs} сек"
        else:
            return f"{secs} сек"
    
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
                raw_array = data.get('data', {}).get('array', [])
                logger.info(f"📊 API вернул {len(raw_array)} участников")
                
                # Отладка: выводим ключи auction_result первого игрока
                if raw_array:
                    first_item = raw_array[0]
                    auction = first_item.get('currentAuctionResult') or {}
                    logger.debug(f"🔍 Ключи auction_result: {list(auction.keys())}")

                for idx, item in enumerate(raw_array):
                    try:
                        if item is None:
                            continue
                        player = item.get('player')
                        if player is None:
                            auction_result = item.get('currentAuctionResult') or {}
                            player_id = auction_result.get('playerId', '')
                            if player_id and player_id in self.player_cache:
                                cached = self.player_cache[player_id]
                                name = cached['name']
                                points = cached['points']
                                game_title = auction_result.get('title', '')
                                game_type = auction_result.get('type', '')
                                game_reward = auction_result.get('ggpReward', 0)
                                game_penalty = auction_result.get('ggpPenalty', 0)
                                timer_started = auction_result.get('timerStartedAt', '')
                                required_action = item.get('requiredAction') or {}
                                action_kind = required_action.get('kind', '') if required_action else ''
                                stream_info = item.get('stream') or []
                                is_streaming = False
                                streaming_platforms = []
                                for stream in stream_info:
                                    if stream.get('online', False):
                                        is_streaming = True
                                        platform = stream.get('platform', 'unknown')
                                        username = stream.get('username', '')
                                        streaming_platforms.append({
                                            'platform': platform,
                                            'username': username
                                        })
                                participants[name] = {
                                    'points': points,
                                    'selected': False,
                                    'game_title': game_title,
                                    'game_type': game_type,
                                    'game_reward': game_reward,
                                    'game_penalty': game_penalty,
                                    'action_kind': action_kind,
                                    'timer_started': timer_started,
                                    'is_streaming': is_streaming,
                                    'streaming_platforms': streaming_platforms,
                                    'timestamp': time.time()
                                }
                            else:
                                continue
                        else:
                            raw_name = player.get('name', '')
                            name = raw_name.strip() if raw_name else ''
                            name_lower = name.lower()
                            if not name or name_lower not in VALID_NAMES:
                                continue
                            points = player.get('ggp', player.get('points', player.get('score', 0)))
                            player_id = player.get('id', '')
                            if player_id:
                                self.player_cache[player_id] = {
                                    'name': name,
                                    'points': points,
                                    'timestamp': time.time()
                                }
                            auction_result = item.get('currentAuctionResult') or {}
                            game_title = auction_result.get('title', '') if auction_result else ''
                            game_type = auction_result.get('type', '') if auction_result else ''
                            game_reward = auction_result.get('ggpReward', 0) if auction_result else 0
                            game_penalty = auction_result.get('ggpPenalty', 0) if auction_result else 0
                            timer_started = auction_result.get('timerStartedAt', '') if auction_result else ''
                            required_action = item.get('requiredAction') or {}
                            action_kind = required_action.get('kind', '') if required_action else ''
                            stream_info = item.get('stream') or []
                            is_streaming = False
                            streaming_platforms = []
                            for stream in stream_info:
                                if stream.get('online', False):
                                    is_streaming = True
                                    platform = stream.get('platform', 'unknown')
                                    username = stream.get('username', '')
                                    streaming_platforms.append({
                                        'platform': platform,
                                        'username': username
                                    })
                            participants[name] = {
                                'points': points,
                                'selected': False,
                                'game_title': game_title,
                                'game_type': game_type,
                                'game_reward': game_reward,
                                'game_penalty': game_penalty,
                                'action_kind': action_kind,
                                'timer_started': timer_started,
                                'is_streaming': is_streaming,
                                'streaming_platforms': streaming_platforms,
                                'timestamp': time.time()
                            }
                    except Exception as e:
                        logger.warning(f"⚠️ [{idx}] Ошибка парсинга: {e}")
                        continue
                if participants:
                    active_name = None
                    latest_time = ""
                    for name, info in participants.items():
                        timer = info.get('timer_started', '')
                        if timer and timer > latest_time:
                            latest_time = timer
                            active_name = name
                    if not active_name:
                        for name, info in participants.items():
                            action = info.get('action_kind', '')
                            if action and action != 'none':
                                active_name = name
                                break
                    if active_name:
                        participants[active_name]['selected'] = True
                missing = [name for name in STREAMERS.values() if name not in participants]
                if missing:
                    logger.warning(f"️ Отсутствуют: {missing}")
                else:
                    logger.info(f"✅ Все 12 стримеров на месте!")
                logger.info(f"✅ Обработано {len(participants)} участников")
                return participants
        except Exception as e:
            logger.error(f"❌ Ошибка при получении данных: {e}", exc_info=True)
            return {}
    
    def _get_leaderboard(self, data: Dict) -> list:
        return sorted(data.items(), key=lambda x: x[1]['points'], reverse=True)
    
    def _get_real_position(self, data: Dict, streamer_name: str) -> int:
        leaderboard = self._get_leaderboard(data)
        for i, (name, _) in enumerate(leaderboard, 1):
            if name == streamer_name:
                return i
        return 0
    
    def _format_streaming_status(self, is_streaming: bool, platforms: List[Dict]) -> str:
        if not is_streaming or not platforms:
            return "🔴 <b>Стрим:</b> Оффлайн"
        platform_emojis = {
            'twitch': '🟣 Twitch',
            'youtube': ' YouTube',
            'kick': ' Kick',
            'telegram': '✈️ Telegram',
            'vk': '🔵 VK',
            'wtv': '📺 WTV',
            'vklive': ' VK Live'
        }
        platform_names = []
        for p in platforms:
            platform = p.get('platform', '').lower()
            emoji = platform_emojis.get(platform, platform.capitalize())
            platform_names.append(emoji)
        return f" <b>Стрим:</b> Онлайн ({', '.join(platform_names)})"
    
    def _format_streaming_status_short(self, is_streaming: bool, platforms: List[Dict]) -> str:
        if is_streaming:
            return "🟢"
        else:
            return "🔴"
    
    def _format_activity_short(self, info: Dict) -> str:
        game_title = info.get('game_title', '')
        game_type = info.get('game_type', '')
        action_kind = info.get('action_kind', '')
        timer_started = info.get('timer_started', '')
        game_reward = info.get('game_reward', 0)
        game_penalty = info.get('game_penalty', 0)
        if game_title:
            reward_str = ""
            if game_reward or game_penalty:
                parts = []
                if game_reward:
                    parts.append(f"+{game_reward}")
                if game_penalty:
                    parts.append(f"-{game_penalty}")
                reward_str = f" ({'/'.join(parts)})"
            if game_type == 'game':
                return f"🎮 Категория: {game_title}{reward_str}"
            else:
                return f"⚡ Категория: {game_title}{reward_str}"
        elif timer_started or (action_kind and action_kind != 'none'):
            if action_kind == 'auction':
                return "🎯 Категория: Аукцион"
            else:
                return "🎡 Категория: Крутит колесо"
        else:
            return "⚪ Категория: Ожидание"
    
    async def get_detailed_streamer_info(self, streamer_name: str) -> Optional[str]:
        try:
            if streamer_name not in STREAMERS.values():
                return None
            data = await self.get_participants_data()
            if streamer_name not in data:
                logger.warning(f"⚠️ Стример '{streamer_name}' не найден")
                return None
            info = data[streamer_name]
            real_position = self._get_real_position(data, streamer_name)
            message = f"👤 <b>{streamer_name}</b>\n"
            message += f"🏆 <b>Место в топе:</b> {real_position} из {len(data)}\n"
            message += f"⭐ <b>Очки:</b> {info['points']}\n"
            is_streaming = info.get('is_streaming', False)
            streaming_platforms = info.get('streaming_platforms', [])
            message += f"{self._format_streaming_status(is_streaming, streaming_platforms)}\n"
            game_title = info.get('game_title', '')
            game_type = info.get('game_type', '')
            action_kind = info.get('action_kind', '')
            timer_started = info.get('timer_started', '')
            
            if game_title:
                game_reward = info.get('game_reward', 0)
                game_penalty = info.get('game_penalty', 0)
                if game_type == 'game':
                    message += f"\n🎮 <b>Игра:</b> {game_title}"
                else:
                    message += f"\n⚡ <b>Действие:</b> {game_title}"
                
                # ⏳ Время в игре (рассчитывается от timerStartedAt)
                if timer_started:
                    try:
                        from datetime import datetime
                        start_dt = datetime.fromisoformat(timer_started.replace('Z', '+00:00'))
                        now = datetime.now(start_dt.tzinfo) if start_dt.tzinfo else datetime.now()
                        elapsed = int((now - start_dt).total_seconds())
                        if elapsed > 0:
                            message += f"\n⏳ <b>Время в игре:</b> {self._format_time_duration(elapsed)}"
                    except Exception as e:
                        logger.debug(f"Ошибка расчета времени для {streamer_name}: {e}")
                
                if game_reward:
                    message += f"\n💰 Награда: +{game_reward}"
                if game_penalty:
                    message += f"\n💔 Штраф: -{game_penalty}"
            elif timer_started or (action_kind and action_kind != 'none'):
                if action_kind == 'auction':
                    message += f"\n <b>Действие:</b> Аукцион"
                else:
                    message += f"\n🎡 <b>Действие:</b> Крутит колесо"
            else:
                message += f"\n⚪ <b>Статус:</b> Не активен"
            return message
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}", exc_info=True)
            return None
    
    async def send_notification(self, message: str):
        if not self.monitoring_groups:
            logger.warning("⚠️ Нет групп для отправки")
            return
        success_count = 0
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
                success_count += 1
            except Exception as e:
                logger.error(f"❌ Ошибка отправки: {e}")
        logger.info(f"✅ Отправлено в {success_count} групп")
    
    def start_monitoring(self):
        if self.monitoring_active:
            logger.warning("⚠️ Мониторинг уже активен!")
            return
        if self.monitor_loop_task is not None and not self.monitor_loop_task.done():
            logger.warning("⚠️ Цикл мониторинга уже работает!")
            return
        self.monitor_loop_task = asyncio.create_task(self.monitor_loop())
        logger.info("🚀 Запущен новый цикл мониторинга")
    
    async def start(self):
        @self.dp.message(Command("debug"))
        async def cmd_debug(message: types.Message):
            if not self.is_admin(message.from_user.id):
                await message.answer("❌ Только админ")
                return
            await message.answer("🔍 Получаю данные...")
            if not self.session:
                self.session = aiohttp.ClientSession()
            try:
                async with self.session.get(API_URL) as response:
                    data = await response.json()
                    text = f"📊 <b>Данные API:</b>\n\n"
                    for idx, item in enumerate(data.get('data', {}).get('array', [])):
                        if item is None:
                            continue
                        player = item.get('player')
                        name = player.get('name', '???') if player else '???'
                        stream_info = item.get('stream') or []
                        online_platforms = []
                        for s in stream_info:
                            if s.get('online', False):
                                online_platforms.append(s.get('platform', 'unknown'))
                        required = item.get('requiredAction') or {}
                        action = required.get('kind', '')
                        auction = item.get('currentAuctionResult') or {}
                        timer = auction.get('timerStartedAt', '')
                        # Выводим все ключи для отладки
                        text += f"<b>{idx+1}. {name}</b>\n"
                        text += f"   Ключи: {list(auction.keys())}\n"
                        text += f"   Стрим: {'онлайн' if online_platforms else 'оффлайн'}\n"
                        text += f"   Action: {action or '-'}\n"
                        text += f"   Timer: {timer or '-'}\n"
                        text += f"   Игра: {auction.get('title', '-')}\n\n"
                    if len(text) > 4000:
                        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
                        for part in parts:
                            await message.answer(part, parse_mode="HTML")
                    else:
                        await message.answer(text, parse_mode="HTML")
            except Exception as e:
                await message.answer(f"❌ Ошибка: {e}")
        
        @self.dp.message(Command("add_group"))
        async def cmd_add_group(message: types.Message):
            if not self.is_admin(message.from_user.id):
                await message.answer("❌ Только админ")
                return
            chat_id = message.chat.id
            thread_id = message.message_thread_id
            for group in self.monitoring_groups:
                if group['chat_id'] == chat_id and group.get('thread_id') == thread_id:
                    await message.answer("✅ Уже добавлена")
                    return
            group_info = {
                'chat_id': chat_id,
                'chat_title': message.chat.title or 'Unknown',
                'thread_id': thread_id,
                'added_at': time.time()
            }
            self.monitoring_groups.append(group_info)
            self.save_groups()
            await message.answer(f"✅ Добавлена\n👥 {message.chat.title}\n🆔 {chat_id}")
            self.start_monitoring()
        
        @self.dp.message(Command("remove_group"))
        async def cmd_remove_group(message: types.Message):
            if not self.is_admin(message.from_user.id):
                await message.answer("❌ Только админ")
                return
            args = message.text.split()[1:] if len(message.text.split()) > 1 else []
            if len(args) == 0:
                chat_id = message.chat.id
                thread_id = message.message_thread_id
            elif len(args) == 1:
                try:
                    chat_id = int(args[0])
                    thread_id = None
                except:
                    await message.answer("❌ Неверный ID")
                    return
            elif len(args) == 2:
                try:
                    chat_id = int(args[0])
                    thread_id = int(args[1])
                except:
                    await message.answer("❌ Неверные ID")
                    return
            else:
                await message.answer("❌ Неверный формат")
                return
            old_len = len(self.monitoring_groups)
            self.monitoring_groups = [
                g for g in self.monitoring_groups 
                if not (g['chat_id'] == chat_id and g.get('thread_id') == thread_id)
            ]
            if len(self.monitoring_groups) < old_len:
                self.save_groups()
                await message.answer(f"✅ Удалена: {chat_id}" + (f" (ветка {thread_id})" if thread_id else ""))
            else:
                await message.answer("❌ Такая группа не найдена в списке")
        
        @self.dp.message(Command("clear_groups"))
        async def cmd_clear_groups(message: types.Message):
            if not self.is_admin(message.from_user.id):
                await message.answer("❌ Только админ")
                return
            count = len(self.monitoring_groups)
            self.monitoring_groups = []
            self.save_groups()
            await message.answer(f"️ Очищено! Удалено групп: {count}")
        
        @self.dp.message(Command("list_groups"))
        async def cmd_list_groups(message: types.Message):
            if not self.is_admin(message.from_user.id):
                await message.answer("❌ Только админ")
                return
            if not self.monitoring_groups:
                await message.answer("📋 Пусто")
                return
            text = " <b>Группы:</b>\n\n"
            for i, group in enumerate(self.monitoring_groups, 1):
                thread_info = f" (ветка #{group['thread_id']})" if group.get('thread_id') else ""
                text += f"{i}. <b>{group['chat_title']}</b>{thread_info}\n"
            await message.answer(text, parse_mode="HTML")
        
        @self.dp.message(Command("test_notify"))
        async def cmd_test_notify(message: types.Message):
            if not self.is_admin(message.from_user.id):
                await message.answer("❌ Только админ")
                return
            await self.send_notification("🔔 <b>Тест</b>\n\n✅ Работает!")
            await message.answer("✅ Отправлено")
        
        @self.dp.message(Command("my_id"))
        async def cmd_my_id(message: types.Message):
            if not self.is_admin(message.from_user.id):
                await message.answer("❌ Только админ")
                return
            chat_id = message.chat.id
            thread_id = message.message_thread_id
            text = f"🆔 Chat ID: <code>{chat_id}</code>\n"
            if thread_id:
                text += f"📌 Thread ID: <code>{thread_id}</code>"
            await message.answer(text, parse_mode="HTML")
        
        @self.dp.message(Command("restart_monitor"))
        async def cmd_restart_monitor(message: types.Message):
            if not self.is_admin(message.from_user.id):
                await message.answer("❌ Только админ")
                return
            self.monitoring_active = False
            if self.monitor_loop_task and not self.monitor_loop_task.done():
                self.monitor_loop_task.cancel()
                await asyncio.sleep(1)
            self.previous_data = {}
            self.monitor_loop_task = asyncio.create_task(self.monitor_loop())
            await message.answer("🔄 Мониторинг перезапущен!")
        
        @self.dp.message(Command("start"))
        async def cmd_start(message: types.Message):
            admin_text = ""
            if self.is_admin(message.from_user.id):
                admin_text = (
                    "\n🔐 <b>Админ:</b>\n"
                    "/add_group, /remove_group, /clear_groups, /list_groups\n"
                    "/test_notify, /my_id, /debug\n"
                    "/restart_monitor - перезапустить мониторинг"
                )
            status_text = f"\n📡 <b>Мониторинг:</b> {'🟢 активен' if self.monitoring_active else '🔴 неактивен'}"
            await message.answer(
                " <b>Бот Nassal.pro</b>\n\n"
                "📋 <b>Команды:</b>\n\n"
                "/status 📊 статус всех стримеров\n"
                "/rating 🏆 рейтинг\n"
                "/points 📊 таблица\n"
                "/streamer [номер/имя] 👤 инфо\n"
                "/list 📝 список\n"
                "/monitor 🔔 мониторинг"
                + status_text
                + admin_text,
                reply_markup=self.get_streamer_keyboard()
            )
        
        @self.dp.message(Command("status"))
        async def cmd_status(message: types.Message):
            await message.answer("🔄 Получаю статусы...")
            data = await self.get_participants_data()
            if not data:
                await message.answer("❌ Не удалось получить данные")
                return
            leaderboard = self._get_leaderboard(data)
            text = " <b>СТАТУС ВСЕХ СТРИМЕРОВ</b>\n"
            text += "━━━━━━━━━━━━━━━━━━━━\n\n"
            for name, info in leaderboard:
                real_position = self._get_real_position(data, name)
                points = info['points']
                if points > 0:
                    points_str = f"+{points}"
                elif points < 0:
                    points_str = str(points)
                else:
                    points_str = "0"
                is_streaming = info.get('is_streaming', False)
                streaming_platforms = info.get('streaming_platforms', [])
                stream_icon = self._format_streaming_status_short(is_streaming, streaming_platforms)
                activity = self._format_activity_short(info)
                text += f" <b>{name}</b> {stream_icon}\n"
                text += f" {real_position} место | ⭐ Очки: {points_str}\n"
                text += f"{activity}\n\n"
            text += "━━━━━━━━━━━━━━━━━━━━\n"
            text += "🟢 — онлайн | 🔴 — оффлайн"
            if len(text) > 4000:
                header = "📊 <b>СТАТУС ВСЕХ СТРИМЕРОВ</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
                footer = "\n━━━━━━━━━━━━━━━━━━━━\n🟢 — онлайн | 🔴 — оффлайн"
                parts = []
                current_part = header
                current_len = len(header)
                for name, info in leaderboard:
                    real_position = self._get_real_position(data, name)
                    points = info['points']
                    if points > 0:
                        points_str = f"+{points}"
                    elif points < 0:
                        points_str = str(points)
                    else:
                        points_str = "0"
                    is_streaming = info.get('is_streaming', False)
                    streaming_platforms = info.get('streaming_platforms', [])
                    stream_icon = self._format_streaming_status_short(is_streaming, streaming_platforms)
                    activity = self._format_activity_short(info)
                    block = f"👤 <b>{name}</b> {stream_icon}\n🏆 {real_position} место | ⭐ Очки: {points_str}\n{activity}\n\n"
                    if current_len + len(block) + len(footer) > 4000:
                        current_part += footer
                        parts.append(current_part)
                        current_part = header + block
                        current_len = len(header) + len(block)
                    else:
                        current_part += block
                        current_len += len(block)
                current_part += footer
                parts.append(current_part)
                for part in parts:
                    await message.answer(part, parse_mode="HTML")
            else:
                await message.answer(text, parse_mode="HTML")
        
        @self.dp.message(Command("list"))
        async def cmd_list(message: types.Message):
            text = "📋 <b>Участники:</b>\n\n"
            for num, name in STREAMERS.items():
                text += f"{num}. <b>{name}</b>\n"
            await message.answer(text, parse_mode="HTML")
        
        @self.dp.message(Command("rating"))
        async def cmd_rating(message: types.Message):
            await message.answer("🔄 Получаю рейтинг...")
            data = await self.get_participants_data()
            if not data:
                await message.answer("❌ Не удалось")
                return
            leaderboard = self._get_leaderboard(data)
            text = "🏆 <b>РЕЙТИНГ</b>\n"
            text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            medals = {1: "🥇", 2: "🥈", 3: "🥉"}
            MAX_WIDTH = 28
            for i, (name, info) in enumerate(leaderboard, 1):
                points = info['points']
                medal = medals.get(i, f"{i}.")
                if points > 0:
                    points_str = f"+{points}"
                elif points < 0:
                    points_str = str(points)
                else:
                    points_str = "0"
                is_streaming = info.get('is_streaming', False)
                stream_emoji = "🟢" if is_streaming else ""
                base = f"{medal} {name} {points_str}"
                visible = self._visible_len(base)
                if visible < MAX_WIDTH:
                    spaces = " " * (MAX_WIDTH - visible)
                else:
                    spaces = " "
                text += f"{base}{spaces}{stream_emoji}\n"
            text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            text += "🟢 — онлайн  |  🔴 — оффлайн"
            await message.answer(text, parse_mode="HTML")
        
        @self.dp.message(Command("points"))
        async def cmd_points(message: types.Message):
            await message.answer("🔄 Получаю...")
            data = await self.get_participants_data()
            if not data:
                await message.answer("❌ Не удалось")
                return
            leaderboard = self._get_leaderboard(data)
            text = " <b>ОЧКИ</b>\n━━━━━━━━━━━━\n\n"
            for i, (name, info) in enumerate(leaderboard, 1):
                points = info['points']
                if points > 0:
                    points_str = f"+{points}"
                elif points < 0:
                    points_str = str(points)
                else:
                    points_str = "0"
                text += f"{i}. <b>{name}</b> — {points_str}\n"
            await message.answer(text, parse_mode="HTML")
        
        @self.dp.message(Command("streamer"))
        async def cmd_streamer(message: types.Message):
            if len(message.text.split()) < 2:
                await message.answer(" Пример: /streamer 1")
                return
            query = message.text.split(maxsplit=1)[1].strip()
            streamer_name = None
            if query.isdigit():
                num = int(query)
                streamer_name = STREAMERS.get(num)
            else:
                query_lower = query.lower().strip()
                if query_lower in STREAMERS_BY_NAME:
                    streamer_name = STREAMERS[STREAMERS_BY_NAME[query_lower]]
                else:
                    for name in STREAMERS.values():
                        if query_lower in name.lower():
                            streamer_name = name
                            break
            if not streamer_name:
                await message.answer(f"❌ '{query}' не найден")
                return
            await message.answer(f" Загрузка...", parse_mode="HTML")
            info = await self.get_detailed_streamer_info(streamer_name)
            if info:
                await message.answer(info, parse_mode="HTML")
            else:
                await message.answer("❌ Не удалось")
        
        @self.dp.message(Command("monitor"))
        async def cmd_monitor(message: types.Message):
            args = message.text.split()[1:] if len(message.text.split()) > 1 else []
            if len(args) == 0:
                chat_id = message.chat.id
                thread_id = message.message_thread_id
                chat_title = message.chat.title or 'Unknown'
            elif len(args) == 1 and self.is_admin(message.from_user.id):
                try:
                    chat_id = int(args[0])
                    thread_id = None
                    chat_title = f"Группа {chat_id}"
                except:
                    await message.answer("❌ Неверный ID")
                    return
            elif len(args) == 2 and self.is_admin(message.from_user.id):
                try:
                    chat_id = int(args[0])
                    thread_id = int(args[1])
                    chat_title = f"Группа {chat_id}"
                except:
                    await message.answer("❌ Неверные ID")
                    return
            else:
                await message.answer("❌ Только админ может указывать ID")
                return
            for group in self.monitoring_groups:
                if group['chat_id'] == chat_id and group.get('thread_id') == thread_id:
                    await message.answer("✅ Уже активен")
                    return
            self.monitoring_groups.append({
                'chat_id': chat_id,
                'chat_title': chat_title,
                'thread_id': thread_id,
                'added_at': time.time()
            })
            self.save_groups()
            await message.answer("🔔 <b>Мониторинг включен!</b>", parse_mode="HTML")
            self.start_monitoring()
        
        @self.dp.message(Command("stop"))
        async def cmd_stop(message: types.Message):
            if not self.is_admin(message.from_user.id):
                await message.answer("❌ Только админ")
                return
            self.monitoring_active = False
            if self.monitor_loop_task and not self.monitor_loop_task.done():
                self.monitor_loop_task.cancel()
            await message.answer("👋 Остановлен")
            if self.session:
                await self.session.close()
            await self.bot.close()
        
        @self.dp.message()
        async def handle_keyboard(message: types.Message):
            text = message.text.strip()
            for num, name in STREAMERS.items():
                if text == f"{num}. {name}" or text == name:
                    await message.answer(f"⏳ Загрузка...", parse_mode="HTML")
                    info = await self.get_detailed_streamer_info(name)
                    if info:
                        await message.answer(info, parse_mode="HTML")
                    else:
                        await message.answer("❌ Не удалось")
                    return
        logger.info("🚀 Бот запущен!")
        if self.monitoring_groups:
            logger.info(" Запускаю мониторинг...")
            self.start_monitoring()
        await self.dp.start_polling(self.bot)
    
    async def monitor_loop(self):
        if self.monitoring_active:
            logger.warning("⚠️ Мониторинг уже активен!")
            return
        logger.info("🔄 Запуск monitor_loop...")
        self.monitoring_active = True
        initial_data = await self.get_participants_data()
        if not initial_data:
            logger.error("❌ Не удалось получить данные")
            self.monitoring_active = False
            return
        self.previous_data = initial_data
        logger.info(f"✅ Запомнено ({len(initial_data)} участников)")
        cycle_count = 0
        while self.monitoring_active:
            try:
                cycle_count += 1
                current_data = await self.get_participants_data()
                if not current_data:
                    await asyncio.sleep(10)
                    continue
                if self.previous_data:
                    changes = self.compare_data(self.previous_data, current_data)
                    if changes:
                        notification = self._format_notification(changes)
                        await self.send_notification(notification)
                        logger.info(f"📤 Отправлено уведомление")
                self.previous_data = current_data
            except Exception as e:
                logger.error(f"❌ Ошибка: {e}")
            await asyncio.sleep(10)
        logger.info("⏹️ Мониторинг остановлен")
    
    def _format_notification(self, changes: list) -> str:
        notification = "🔔 <b>ИЗМЕНЕНИЯ НА NASSAL.PRO</b>\n"
        notification += "━━━━━━━━━━━━━━━━━━━━\n\n"
        notification += "\n\n".join(changes)
        notification += "\n\n━━━━━━━━━━━━━━━━━━━━"
        return notification
    
    def compare_data(self, old_data: Dict, new_data: Dict) -> list:
        changes = []
        old_positions = {}
        new_positions = {}
        old_leaderboard = self._get_leaderboard(old_data)
        new_leaderboard = self._get_leaderboard(new_data)
        for i, (name, _) in enumerate(old_leaderboard, 1):
            old_positions[name] = i
        for i, (name, _) in enumerate(new_leaderboard, 1):
            new_positions[name] = i
        position_changes = []
        for name in new_data.keys():
            if name in old_positions and name in new_positions:
                old_pos = old_positions[name]
                new_pos = new_positions[name]
                if old_pos != new_pos:
                    diff = old_pos - new_pos
                    if diff > 0:
                        word_num = self._number_to_word(diff)
                        pos_word = self._get_position_word(diff)
                        position_changes.append(
                            f"🚀 <b>{name}</b>: было {old_pos} место 🟢 стало {new_pos} место\n"
                            f"   ️ поднялся на {word_num} {pos_word}"
                        )
                    else:
                        abs_diff = abs(diff)
                        word_num = self._number_to_word(abs_diff)
                        pos_word = self._get_position_word(abs_diff)
                        position_changes.append(
                            f"📉 <b>{name}</b>: было {old_pos} место 🔻 стало {new_pos} место\n"
                            f"   ↘️ упал на {word_num} {pos_word}"
                        )
        if position_changes:
            changes.append("📊 <b>ПОЗИЦИИ:</b>\n\n" + "\n\n".join(position_changes))
        points_changes = []
        for name, data in new_data.items():
            if name in old_data:
                old_points = old_data[name].get('points', 0)
                new_points = data.get('points', 0)
                if old_points != new_points:
                    diff = new_points - old_points
                    if diff > 0:
                        emoji = "💚"
                        sign = "+"
                    else:
                        emoji = ""
                        sign = ""
                    points_changes.append(
                        f"{emoji} <b>{name}</b>: {old_points} → {new_points} ({sign}{diff})"
                    )
        if points_changes:
            changes.append("💰 <b>ОЧКИ:</b>\n\n" + "\n\n".join(points_changes))
        game_changes = []
        for name, data in new_data.items():
            if name in old_data:
                old_game = old_data[name].get('game_title', '')
                new_game = data.get('game_title', '')
                if old_game != new_game:
                    if not old_game and new_game:
                        game_changes.append(
                            f"🎮 <b>{name}</b> начал играть: <b>{new_game}</b>"
                        )
                    elif old_game and not new_game:
                        game_changes.append(
                            f"⏹️ <b>{name}</b> закончил: <b>{old_game}</b>"
                        )
                    elif old_game and new_game:
                        game_changes.append(
                            f"🔄 <b>{name}</b> сменил игру:\n{old_game} → {new_game}"
                        )
        if game_changes:
            changes.append(" <b>ИГРЫ:</b>\n\n" + "\n\n".join(game_changes))
        return changes

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
