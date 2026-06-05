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

class NassalMonitor:
    def __init__(self, bot_token: str):
        self.bot = Bot(token=bot_token)
        self.dp = Dispatcher()
        self.previous_data: Dict = {}
        self.session: Optional[aiohttp.ClientSession] = None
        self.monitoring_groups: List[Dict] = self.load_groups()
        self.monitoring_active: bool = False
        self.player_cache: Dict[str, Dict] = {}
    
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
        """Полный формат статуса стрима для детальной информации"""
        if not is_streaming or not platforms:
            return "🔴 <b>Стрим:</b> Оффлайн"
        
        platform_emojis = {
            'twitch': '🟣 Twitch',
            'youtube': '🔴 YouTube',
            'kick': '🟢 Kick',
            'telegram': '️ Telegram',
            'vk': ' VK',
            'wtv': ' WTV',
            'vklive': '🔵 VK Live'
        }
        
        platform_names = []
        for p in platforms:
            platform = p.get('platform', '').lower()
            emoji = platform_emojis.get(platform, platform.capitalize())
            platform_names.append(emoji)
        
        return f"🟢 <b>Стрим:</b> Онлайн ({', '.join(platform_names)})"
    
    def _format_streaming_status_short(self, is_streaming: bool, platforms: List[Dict]) -> str:
        """Короткий формат: только  или 🔴"""
        if is_streaming:
            return "🟢"
        else:
            return "🔴"
    
    def _format_activity_short(self, info: Dict) -> str:
        """Короткий формат активности для списка"""
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
                return " Категория: Аукцион"
            else:
                return "🎡 Категория: Крутит колесо"
        else:
            return " Категория: Ожидание"
    
    async def get_detailed_streamer_info(self, streamer_name: str) -> Optional[str]:
        """Получает подробную информацию о стримере"""
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
                
                if game_reward:
                    message += f"\n💰 Награда: +{game_reward}"
                if game_penalty:
                    message += f"\n💔 Штраф: -{game_penalty}"
            
            elif timer_started or (action_kind and action_kind != 'none'):
                if action_kind == 'auction':
                    message += f"\n🎯 <b>Действие:</b> Аукцион"
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
                logger.error(f" Ошибка отправки: {e}")
        
        logger.info(f"✅ Отправлено в {success_count} групп")
    
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
                        
                        text += f"<b>{idx+1}. {name}</b>\n"
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
            
            await message.answer(f"✅ Добавлена\n {message.chat.title}\n🆔 {chat_id}")
            
            if not self.monitoring_active:
                asyncio.create_task(self.monitor_loop())
        
        @self.dp.message(Command("remove_group"))
        async def cmd_remove_group(message: types.Message):
            if not self.is_admin(message.from_user.id):
                await message.answer("❌ Только админ")
                return
            
            chat_id = message.chat.id
            thread_id = message.message_thread_id
            
            self.monitoring_groups = [
                g for g in self.monitoring_groups 
                if not (g['chat_id'] == chat_id and g.get('thread_id') == thread_id)
            ]
            
            self.save_groups()
            await message.answer("✅ Удалена")
        
        @self.dp.message(Command("list_groups"))
        async def cmd_list_groups(message: types.Message):
            if not self.is_admin(message.from_user.id):
                await message.answer("❌ Только админ")
                return
            
            if not self.monitoring_groups:
                await message.answer("📋 Пусто")
                return
            
            text = "📋 <b>Группы:</b>\n\n"
            for i, group in enumerate(self.monitoring_groups, 1):
                thread_info = f" (ветка #{group['thread_id']})" if group.get('thread_id') else ""
                text += f"{i}. <b>{group['chat_title']}</b>{thread_info}\n"
            
            await message.answer(text, parse_mode="HTML")
        
        @self.dp.message(Command("test_notify"))
        async def cmd_test_notify(message: types.Message):
            if not self.is_admin(message.from_user.id):
                await message.answer(" Только админ")
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
            
            text = f" Chat ID: <code>{chat_id}</code>\n"
            if thread_id:
                text += f"📌 Thread ID: <code>{thread_id}</code>"
            
            await message.answer(text, parse_mode="HTML")
        
        @self.dp.message(Command("start"))
        async def cmd_start(message: types.Message):
            admin_text = ""
            if self.is_admin(message.from_user.id):
                admin_text = (
                    "\n🔐 <b>Админ:</b>\n"
                    "/add_group, /remove_group, /list_groups\n"
                    "/test_notify, /my_id, /debug"
                )
            
            await message.answer(
                "🤖 <b>Бот Nassal.pro</b>\n\n"
                "📋 <b>Команды:</b>\n\n"
                "/status 📊 статус всех стримеров\n"
                "/rating 🏆 рейтинг\n"
                "/points 📊 таблица\n"
                "/streamer [номер/имя] 👤 инфо\n"
                "/list 📝 список\n"
                "/monitor 🔔 мониторинг"
                + admin_text,
                reply_markup=self.get_streamer_keyboard()
            )
        
        @self.dp.message(Command("status"))
        async def cmd_status(message: types.Message):
            """Показывает статус всех стримеров в компактном формате"""
            await message.answer("🔄 Получаю статусы...")
            data = await self.get_participants_data()
            
            if not data:
                await message.answer("❌ Не удалось получить данные")
                return
            
            leaderboard = self._get_leaderboard(data)
            
            text = "📊 <b>СТАТУС ВСЕХ СТРИМЕРОВ</b>\n"
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
                
                text += f"👤 <b>{name}</b> {stream_icon}\n"
                text += f"🏆 {real_position} место |  Очки: {points_str}\n"
                text += f"{activity}\n\n"
            
            text += "━━━━━━━━━━━━━━━━━━━━\n"
            text += "🟢 — онлайн | 🔴 — оффлайн"
            
            if len(text) > 4000:
                header = " <b>СТАТУС ВСЕХ СТРИМЕРОВ</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
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
            
            text = "🏆 <b>РЕЙТИНГ</b>\n━━━━━━━━━━━━\n\n"
            
            medals = {1: "🥇", 2: "", 3: "🥉"}
            
            for i, (name, info) in enumerate(leaderboard, 1):
                points = info['points']
                medal = medals.get(i, f"{i}.")
                
                if points > 0:
                    points_str = f"+{points}"
                    emoji = "🟢"
                elif points < 0:
                    points_str = str(points)
                    emoji = "🔴"
                else:
                    points_str = "0"
                    emoji = "⚪"
                
                text += f"{medal} {name} — {emoji} <b>{points_str}</b>\n"
            
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
                await message.answer("❌ Пример: /streamer 1")
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
            
            await message.answer(f"⏳ Загрузка...", parse_mode="HTML")
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
            
            if not self.monitoring_active:
                asyncio.create_task(self.monitor_loop())
        
        @self.dp.message(Command("stop"))
        async def cmd_stop(message: types.Message):
            if not self.is_admin(message.from_user.id):
                await message.answer(" Только админ")
                return
            
            self.monitoring_active = False
            await message.answer(" Остановлен")
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
            logger.info("🔄 Запускаю мониторинг...")
            asyncio.create_task(self.monitor_loop())
        
        await self.dp.start_polling(self.bot)
    
    async def monitor_loop(self):
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
                        logger.info(f"📤 Отправлено")
                
                self.previous_data = current_data
                
            except Exception as e:
                logger.error(f"❌ Ошибка: {e}")
            
            await asyncio.sleep(10)
    
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
        
        # 1. ИЗМЕНЕНИЯ ПОЗИЦИЙ
        position_changes = []
        for name in new_data.keys():
            if name in old_positions and name in new_positions:
                old_pos = old_positions[name]
                new_pos = new_positions[name]
                
                if old_pos != new_pos:
                    diff = old_pos - new_pos
                    if diff > 0:
                        emoji = "🚀"
                        direction = f"поднялся на {diff}"
                    else:
                        emoji = ""
                        direction = f"упал на {abs(diff)}"
                    
                    position_changes.append(
                        f"{emoji} <b>{name}</b>: {old_pos} → {new_pos} ({direction})"
                    )
        
        if position_changes:
            changes.append("📊 <b>ПОЗИЦИИ:</b>\n" + "\n".join(position_changes))
        
        # 2. ИЗМЕНЕНИЯ ОЧКОВ
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
            changes.append("💰 <b>ОЧКИ:</b>\n" + "\n".join(points_changes))
        
        # 3. ИЗМЕНЕНИЯ ИГР
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
                            f" <b>{name}</b> сменил игру:\n{old_game} → {new_game}"
                        )
        
        if game_changes:
            changes.append("🎮 <b>ИГРЫ:</b>\n" + "\n".join(game_changes))
        
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
