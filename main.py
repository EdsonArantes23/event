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
        self.hltb_cache: Dict[str, str] = {}

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
            logger.info(f" Сохранено групп: {len(self.monitoring_groups)}")
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
        if not seconds or seconds < 0:
            return "0 сек"
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        if hours > 0:
            return f"{hours} ч {minutes} мин {secs} сек"
        elif minutes > 0:
            return f"{minutes} мин {secs} сек"
        return f"{secs} сек"

    def _parse_hltb_time(self, time_str: str) -> str:
        if not time_str:
            return ""
        time_str = time_str.strip().lower()
        hours = 0
        minutes = 0
        hour_match = re.search(r'(\d+)\s*(?:час|ч)', time_str)
        if hour_match:
            hours = int(hour_match.group(1))
        min_match = re.search(r'(\d+)\s*(?:минут|мин)', time_str)
        if min_match:
            minutes = int(min_match.group(1))
        if hours > 0 or minutes > 0:
            if hours > 0:
                return f"{hours} ч {minutes} мин"
            else:
                return f"{minutes} мин"
        return time_str

    async def fetch_hltb(self, content_item_id: str, title: str) -> str:
        """Пытается получить HLTB время из API контента"""
        if not content_item_id:
            return ""
        if content_item_id in self.hltb_cache:
            return self.hltb_cache[content_item_id]
        
        try:
            url = f"https://api-game.nassal.pro/api/public/content/{content_item_id}"
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    content_data = data.get('data', data)
                    hltb = content_data.get('hltb') or content_data.get('hltbText', '')
                    if hltb:
                        self.hltb_cache[content_item_id] = self._parse_hltb_time(hltb)
                        return self.hltb_cache[content_item_id]
        except Exception as e:
            logger.debug(f"Не удалось получить HLTB для {title}: {e}")
        return ""

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
                
                for idx, item in enumerate(raw_array):
                    try:
                        if item is None:
                            continue
                        
                        player = item.get('player')
                        auction_result = item.get('currentAuctionResult') or {}
                        
                        if player is None and auction_result:
                            player_id = auction_result.get('playerId', '')
                            if player_id and player_id in self.player_cache:
                                cached = self.player_cache[player_id]
                                name = cached['name']
                                points = cached['points']
                            else:
                                continue
                        elif player:
                            raw_name = player.get('name', '')
                            name = raw_name.strip() if raw_name else ''
                            if not name or name.lower() not in VALID_NAMES:
                                continue
                            points = player.get('ggp', player.get('points', player.get('score', 0)))
                            player_id = player.get('id', '')
                            if player_id:
                                self.player_cache[player_id] = {'name': name, 'points': points, 'timestamp': time.time()}
                        else:
                            continue
                        
                        game_title = auction_result.get('title', '')
                        game_type = auction_result.get('type', '')
                        game_reward = auction_result.get('ggpReward', 0)
                        game_penalty = auction_result.get('ggpPenalty', 0)
                        timer_started = auction_result.get('timerStartedAt', '')
                        content_item_id = auction_result.get('contentItemId', '')
                        
                        # ✅ Точное время игры с сайта
                        played_time = int(auction_result.get('timerAccumulatedSec', 0) or 0)
                        if not played_time:
                            played_time = int(auction_result.get('finalSpentSec', 0) or 0)
                        
                        required_action = item.get('requiredAction') or {}
                        action_kind = required_action.get('kind', '') if required_action else ''
                        
                        stream_info = item.get('stream') or []
                        is_streaming = False
                        streaming_platforms = []
                        for stream in stream_info:
                            if stream.get('online', False):
                                is_streaming = True
                                streaming_platforms.append({
                                    'platform': stream.get('platform', 'unknown'),
                                    'username': stream.get('username', '')
                                })
                        
                        # Асинхронно запрашиваем HLTB только если игра активна и есть ID
                        hltb_time = ""
                        if game_title and content_item_id:
                            hltb_time = await self.fetch_hltb(content_item_id, game_title)
                        
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
                            'played_time': played_time,
                            'hltb_time': hltb_time,
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
                
                missing = [n for n in STREAMERS.values() if n not in participants]
                if missing:
                    logger.warning(f"⚠️ Отсутствуют: {missing}")
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
            'twitch': '🟣 Twitch', 'youtube': '🔴 YouTube', 'kick': '🟢 Kick',
            'telegram': '✈️ Telegram', 'vk': '🔵 VK', 'wtv': ' WTV', 'vklive': ' VK Live'
        }
        platform_names = []
        for p in platforms:
            platform = p.get('platform', '').lower()
            emoji = platform_emojis.get(platform, platform.capitalize())
            platform_names.append(emoji)
        return f"🟢 <b>Стрим:</b> Онлайн ({', '.join(platform_names)})"

    def _format_streaming_status_short(self, is_streaming: bool, platforms: List[Dict]) -> str:
        return "🟢" if is_streaming else "🔴"

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
                if game_reward: parts.append(f"+{game_reward}")
                if game_penalty: parts.append(f"-{game_penalty}")
                reward_str = f" ({'/'.join(parts)})"
            if game_type == 'game':
                return f"🎮 Категория: {game_title}{reward_str}"
            else:
                return f"⚡ Категория: {game_title}{reward_str}"
        elif timer_started or (action_kind and action_kind != 'none'):
            if action_kind == 'auction':
                return "🎯 Категория: Аукцион"
            else:
                return " Категория: Крутит колесо"
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
            message += f"{self._format_streaming_status(info.get('is_streaming', False), info.get('streaming_platforms', []))}\n"
            
            game_title = info.get('game_title', '')
            game_type = info.get('game_type', '')
            action_kind = info.get('action_kind', '')
            played_time = info.get('played_time', 0)
            hltb_time = info.get('hltb_time', '')
            
            if game_title:
                message += f"\n🎮 <b>Игра:</b> {game_title}" if game_type == 'game' else f"\n⚡ <b>Действие:</b> {game_title}"
                
                # ✅ Вывод HLTB и времени в игре
                if hltb_time:
                    message += f"\n⏱️ <b>HLTB:</b> {hltb_time}"
                if played_time and played_time > 0:
                    message += f"\n⏳ <b>Время в игре:</b> {self._format_time_duration(played_time)}"
                
                if info.get('game_reward', 0):
                    message += f"\n Награда: +{info['game_reward']}"
                if info.get('game_penalty', 0):
                    message += f"\n💔 Штраф: -{info['game_penalty']}"
            elif action_kind:
                message += f"\n🎯 <b>Действие:</b> Аукцион" if action_kind == 'auction' else f"\n🎡 <b>Действие:</b> Крутит колесо"
            else:
                message += f"\n⚪ <b>Статус:</b> Не активен"
                
            return message
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}", exc_info=True)
            return None

    async def send_notification(self, message: str):
        if not self.monitoring_groups:
            logger.warning("️ Нет групп для отправки")
            return
        success_count = 0
        for group in self.monitoring_groups:
            try:
                await self.bot.send_message(
                    chat_id=group['chat_id'],
                    text=message,
                    parse_mode="HTML",
                    message_thread_id=group.get('thread_id')
                )
                success_count += 1
            except Exception as e:
                logger.error(f"❌ Ошибка отправки: {e}")
        logger.info(f"✅ Отправлено в {success_count} групп")

    def start_monitoring(self):
        if self.monitoring_active or (self.monitor_loop_task and not self.monitor_loop_task.done()):
            logger.warning("⚠️ Мониторинг уже активен!")
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
                    text = "📊 <b>Данные API:</b>\n\n"
                    for idx, item in enumerate(data.get('data', {}).get('array', [])):
                        if item is None: continue
                        player = item.get('player')
                        name = player.get('name', '???') if player else '???'
                        auction = item.get('currentAuctionResult') or {}
                        text += f"<b>{idx+1}. {name}</b>\n"
                        text += f"   timerAccumulatedSec: {auction.get('timerAccumulatedSec', '-')}\n"
                        text += f"   contentItemId: {auction.get('contentItemId', '-')}\n"
                        text += f"   Игра: {auction.get('title', '-')}\n\n"
                    if len(text) > 4000:
                        for i in range(0, len(text), 4000):
                            await message.answer(text[i:i+4000], parse_mode="HTML")
                    else:
                        await message.answer(text, parse_mode="HTML")
            except Exception as e:
                await message.answer(f"❌ Ошибка: {e}")

        @self.dp.message(Command("add_group"))
        async def cmd_add_group(message: types.Message):
            if not self.is_admin(message.from_user.id):
                await message.answer("❌ Только админ")
                return
            chat_id, thread_id = message.chat.id, message.message_thread_id
            for g in self.monitoring_groups:
                if g['chat_id'] == chat_id and g.get('thread_id') == thread_id:
                    await message.answer("✅ Уже добавлена")
                    return
            self.monitoring_groups.append({'chat_id': chat_id, 'chat_title': message.chat.title or 'Unknown', 'thread_id': thread_id, 'added_at': time.time()})
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
                chat_id, thread_id = message.chat.id, message.message_thread_id
            elif len(args) == 1:
                try: chat_id, thread_id = int(args[0]), None
                except: return await message.answer("❌ Неверный ID")
            elif len(args) == 2:
                try: chat_id, thread_id = int(args[0]), int(args[1])
                except: return await message.answer("❌ Неверные ID")
            else: return await message.answer("❌ Неверный формат")
            
            old_len = len(self.monitoring_groups)
            self.monitoring_groups = [g for g in self.monitoring_groups if not (g['chat_id'] == chat_id and g.get('thread_id') == thread_id)]
            if len(self.monitoring_groups) < old_len:
                self.save_groups()
                await message.answer(f"✅ Удалена: {chat_id}" + (f" (ветка {thread_id})" if thread_id else ""))
            else:
                await message.answer("❌ Такая группа не найдена в списке")

        @self.dp.message(Command("clear_groups"))
        async def cmd_clear_groups(message: types.Message):
            if not self.is_admin(message.from_user.id):
                await message.answer(" Только админ")
                return
            count = len(self.monitoring_groups)
            self.monitoring_groups = []
            self.save_groups()
            await message.answer(f"🗑️ Очищено! Удалено групп: {count}")

        @self.dp.message(Command("list_groups"))
        async def cmd_list_groups(message: types.Message):
            if not self.is_admin(message.from_user.id):
                await message.answer(" Только админ")
                return
            if not self.monitoring_groups:
                await message.answer(" Пусто")
                return
            text = "📋 <b>Группы:</b>\n\n"
            for i, g in enumerate(self.monitoring_groups, 1):
                text += f"{i}. <b>{g['chat_title']}</b>{f' (ветка #{g[\"thread_id\"]})' if g.get('thread_id') else ''}\n"
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
            text = f"🆔 Chat ID: <code>{message.chat.id}</code>\n"
            if message.message_thread_id:
                text += f"📌 Thread ID: <code>{message.message_thread_id}</code>"
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
            admin_text = "\n🔐 <b>Админ:</b>\n/add_group, /remove_group, /clear_groups, /list_groups\n/test_notify, /my_id, /debug\n/restart_monitor" if self.is_admin(message.from_user.id) else ""
            await message.answer(
                f"🤖 <b>Бот Nassal.pro</b>\n\n📋 <b>Команды:</b>\n\n/status  статус всех стримеров\n/rating  рейтинг\n/points 📊 таблица\n/streamer [номер/имя] 👤 инфо\n/list 📝 список\n/monitor 🔔 мониторинг\n\n📡 <b>Мониторинг:</b> {'🟢 активен' if self.monitoring_active else '🔴 неактивен'}{admin_text}",
                reply_markup=self.get_streamer_keyboard()
            )

        @self.dp.message(Command("status"))
        async def cmd_status(message: types.Message):
            await message.answer(" Получаю статусы...")
            data = await self.get_participants_data()
            if not data:
                await message.answer("❌ Не удалось получить данные")
                return
            leaderboard = self._get_leaderboard(data)
            text = "📊 <b>СТАТУС ВСЕХ СТРИМЕРОВ</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            for name, info in leaderboard:
                text += f"👤 <b>{name}</b> {self._format_streaming_status_short(info.get('is_streaming', False), info.get('streaming_platforms', []))}\n"
                text += f"🏆 {self._get_real_position(data, name)} место | ⭐ Очки: {'+' + str(info['points']) if info['points'] > 0 else info['points']}\n"
                text += f"{self._format_activity_short(info)}\n\n"
            text += "━━━━━━━━━━━━━━━━━━━━\n🟢 — онлайн | 🔴 — оффлайн"
            if len(text) > 4000:
                header, footer = "📊 <b>СТАТУС ВСЕХ СТРИМЕРОВ</b>\n━━━━━━━━━━━━━━━━━━━━\n\n", "\n━━━━━━━━━━━━━━━━━━━━\n — онлайн | 🔴 — оффлайн"
                parts, current, curr_len = [], header, len(header)
                for name, info in leaderboard:
                    block = f"👤 <b>{name}</b> {self._format_streaming_status_short(info.get('is_streaming', False), info.get('streaming_platforms', []))}\n🏆 {self._get_real_position(data, name)} место | ⭐ Очки: {'+' + str(info['points']) if info['points'] > 0 else info['points']}\n{self._format_activity_short(info)}\n\n"
                    if curr_len + len(block) + len(footer) > 4000:
                        current += footer
                        parts.append(current)
                        current, curr_len = header + block, len(header) + len(block)
                    else:
                        current += block
                        curr_len += len(block)
                parts.append(current + footer)
                for p in parts: await message.answer(p, parse_mode="HTML")
            else:
                await message.answer(text, parse_mode="HTML")

        @self.dp.message(Command("list"))
        async def cmd_list(message: types.Message):
            await message.answer("📋 <b>Участники:</b>\n\n" + "\n".join(f"{n}. <b>{nm}</b>" for n, nm in STREAMERS.items()), parse_mode="HTML")

        @self.dp.message(Command("rating"))
        async def cmd_rating(message: types.Message):
            await message.answer("🔄 Получаю рейтинг...")
            data = await self.get_participants_data()
            if not data: return await message.answer("❌ Не удалось")
            leaderboard = self._get_leaderboard(data)
            text = "🏆 <b>РЕЙТИНГ</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            medals = {1: "🥇", 2: "🥈", 3: "🥉"}
            MAX_WIDTH = 28
            for i, (name, info) in enumerate(leaderboard, 1):
                pts = f"+{info['points']}" if info['points'] > 0 else str(info['points'])
                emoji = "" if info.get('is_streaming', False) else "🔴"
                base = f"{medals.get(i, f'{i}.')} {name} {pts}"
                text += f"{base}{' ' * max(1, MAX_WIDTH - self._visible_len(base))}{emoji}\n"
            text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n — онлайн  |  🔴 — оффлайн"
            await message.answer(text, parse_mode="HTML")

        @self.dp.message(Command("points"))
        async def cmd_points(message: types.Message):
            await message.answer("🔄 Получаю...")
            data = await self.get_participants_data()
            if not data: return await message.answer(" Не удалось")
            text = " <b>ОЧКИ</b>\n━━━━━━━━━━━━\n\n"
            for i, (name, info) in enumerate(self._get_leaderboard(data), 1):
                text += f"{i}. <b>{name}</b> — {'+' + str(info['points']) if info['points'] > 0 else info['points']}\n"
            await message.answer(text, parse_mode="HTML")

        @self.dp.message(Command("streamer"))
        async def cmd_streamer(message: types.Message):
            if len(message.text.split()) < 2: return await message.answer("❌ Пример: /streamer 1")
            query = message.text.split(maxsplit=1)[1].strip()
            name = STREAMERS.get(int(query)) if query.isdigit() else STREAMERS.get(STREAMERS_BY_NAME.get(query.lower())) or next((n for n in STREAMERS.values() if query.lower() in n.lower()), None)
            if not name: return await message.answer(f"❌ '{query}' не найден")
            await message.answer(" Загрузка...", parse_mode="HTML")
            info = await self.get_detailed_streamer_info(name)
            await message.answer(info or "❌ Не удалось", parse_mode="HTML")

        @self.dp.message(Command("monitor"))
        async def cmd_monitor(message: types.Message):
            args = message.text.split()[1:] if len(message.text.split()) > 1 else []
            if len(args) == 0:
                chat_id, thread_id, title = message.chat.id, message.message_thread_id, message.chat.title or 'Unknown'
            elif len(args) == 1 and self.is_admin(message.from_user.id):
                try: chat_id, thread_id, title = int(args[0]), None, f"Группа {args[0]}"
                except: return await message.answer(" Неверный ID")
            elif len(args) == 2 and self.is_admin(message.from_user.id):
                try: chat_id, thread_id, title = int(args[0]), int(args[1]), f"Группа {args[0]}"
                except: return await message.answer("❌ Неверные ID")
            else: return await message.answer("❌ Только админ может указывать ID")
            
            for g in self.monitoring_groups:
                if g['chat_id'] == chat_id and g.get('thread_id') == thread_id:
                    return await message.answer("✅ Уже активен")
            self.monitoring_groups.append({'chat_id': chat_id, 'chat_title': title, 'thread_id': thread_id, 'added_at': time.time()})
            self.save_groups()
            await message.answer("🔔 <b>Мониторинг включен!</b>", parse_mode="HTML")
            self.start_monitoring()

        @self.dp.message(Command("stop"))
        async def cmd_stop(message: types.Message):
            if not self.is_admin(message.from_user.id): return await message.answer("❌ Только админ")
            self.monitoring_active = False
            if self.monitor_loop_task and not self.monitor_loop_task.done(): self.monitor_loop_task.cancel()
            await message.answer("👋 Остановлен")
            if self.session: await self.session.close()
            await self.bot.close()

        @self.dp.message()
        async def handle_keyboard(message: types.Message):
            text = message.text.strip()
            for num, name in STREAMERS.items():
                if text == f"{num}. {name}" or text == name:
                    await message.answer("⏳ Загрузка...", parse_mode="HTML")
                    info = await self.get_detailed_streamer_info(name)
                    return await message.answer(info or "❌ Не удалось", parse_mode="HTML")

        logger.info("🚀 Бот запущен!")
        if self.monitoring_groups:
            logger.info("🔄 Запускаю мониторинг...")
            self.start_monitoring()
        await self.dp.start_polling(self.bot)

    async def monitor_loop(self):
        if self.monitoring_active: return
        logger.info("🔄 Запуск monitor_loop...")
        self.monitoring_active = True
        self.previous_data = await self.get_participants_data()
        if not self.previous_data:
            logger.error("❌ Не удалось получить данные")
            self.monitoring_active = False
            return
        logger.info(f"✅ Запомнено ({len(self.previous_data)} участников)")
        while self.monitoring_active:
            try:
                current_data = await self.get_participants_data()
                if current_data and self.previous_data:
                    changes = self.compare_data(self.previous_data, current_data)
                    if changes:
                        await self.send_notification(self._format_notification(changes))
                        logger.info("📤 Отправлено уведомление")
                self.previous_data = current_data
            except Exception as e:
                logger.error(f"❌ Ошибка: {e}")
            await asyncio.sleep(10)
        logger.info("⏹️ Мониторинг остановлен")

    def _format_notification(self, changes: list) -> str:
        return f" <b>ИЗМЕНЕНИЯ НА NASSAL.PRO</b>\n━━━━━━━━━━━━━━━━━━━━\n\n" + "\n\n".join(changes) + "\n\n━━━━━━━━━━━━━━━━━━━━"

    def compare_data(self, old_data: Dict, new_data: Dict) -> list:
        changes = []
        old_pos = {n: i for i, (n, _) in enumerate(self._get_leaderboard(old_data), 1)}
        new_pos = {n: i for i, (n, _) in enumerate(self._get_leaderboard(new_data), 1)}
        
        pos_changes = []
        for name in new_data:
            if name in old_pos and name in new_pos and old_pos[name] != new_pos[name]:
                diff = old_pos[name] - new_pos[name]
                if diff > 0:
                    pos_changes.append(f"🚀 <b>{name}</b>: было {old_pos[name]} место  стало {new_pos[name]} место\n   ↗️ поднялся на {self._number_to_word(diff)} {self._get_position_word(diff)}")
                else:
                    pos_changes.append(f" <b>{name}</b>: было {old_pos[name]} место 🔻 стало {new_pos[name]} место\n   ↘️ упал на {self._number_to_word(abs(diff))} {self._get_position_word(abs(diff))}")
        if pos_changes: changes.append(f"📊 <b>ПОЗИЦИИ:</b>\n\n" + "\n\n".join(pos_changes))
        
        pts_changes = []
        for name, d in new_data.items():
            if name in old_data and old_data[name]['points'] != d['points']:
                diff = d['points'] - old_data[name]['points']
                pts_changes.append(f"{'💚' if diff > 0 else '💔'} <b>{name}</b>: {old_data[name]['points']} → {d['points']} ({'+' if diff > 0 else ''}{diff})")
        if pts_changes: changes.append(f"💰 <b>ОЧКИ:</b>\n\n" + "\n\n".join(pts_changes))
        
        game_changes = []
        for name, d in new_data.items():
            if name in old_data and old_data[name]['game_title'] != d['game_title']:
                old_g, new_g = old_data[name]['game_title'], d['game_title']
                if not old_g and new_g: game_changes.append(f"🎮 <b>{name}</b> начал играть: <b>{new_g}</b>")
                elif old_g and not new_g: game_changes.append(f"⏹️ <b>{name}</b> закончил: <b>{old_g}</b>")
                elif old_g and new_g: game_changes.append(f"🔄 <b>{name}</b> сменил игру:\n{old_g} → {new_g}")
        if game_changes: changes.append(f"🎮 <b>ИГРЫ:</b>\n\n" + "\n\n".join(game_changes))
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
