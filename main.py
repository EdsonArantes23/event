import asyncio
import time
import os
from typing import Dict, Optional
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.action_chains import ActionChains
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

class NassalMonitor:
    def __init__(self, bot_token: str, chat_id: int):
        self.bot = Bot(token=bot_token)
        self.dp = Dispatcher()
        self.chat_id = chat_id
        self.previous_data: Dict = {}
        
        self.chrome_options = Options()
        self.chrome_options.add_argument("--headless")
        self.chrome_options.add_argument("--no-sandbox")
        self.chrome_options.add_argument("--disable-dev-shm-usage")
        self.chrome_options.add_argument("--window-size=1920,1080")
        self.chrome_options.add_argument("--disable-gpu")
        self.chrome_options.add_argument("--disable-software-rasterizer")
        self.chrome_options.add_argument("--disable-extensions")
        self.chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        self.driver = webdriver.Chrome(options=self.chrome_options)
        self.driver.set_page_load_timeout(30)
        self.url = "https://nassal.pro/"
        
    def click_first_popup(self) -> bool:
        """Кликает по первому всплывающему окну (письму/сообщению)"""
        try:
            logger.info("🔍 Ищу первый попап (письмо)...")
            
            # Ждем появления любого кликабельного элемента на первом экране
            time.sleep(3)  # Даем время на загрузку первого экрана
            
            # Делаем скриншот для отладки
            try:
                self.driver.save_screenshot("debug_step1_first_screen.png")
                logger.info("📸 Скриншот первого экрана сохранен")
            except:
                pass
            
            # Пробуем найти кнопку/элемент для клика
            button_clicked = False
            
            # Вариант 1: Ищем кнопку с любым текстом
            try:
                buttons = self.driver.find_elements(By.TAG_NAME, "button")
                for btn in buttons:
                    if btn.is_displayed() and btn.is_enabled():
                        text = btn.text.strip()
                        if text and len(text) > 0:
                            logger.info(f"✅ Найден элемент на первом экране: '{text}'")
                            ActionChains(self.driver).move_to_element(btn).click().perform()
                            button_clicked = True
                            time.sleep(2)  # Ждем перехода на следующий экран
                            break
            except Exception as e:
                logger.warning(f"⚠️ Не удалось найти кнопку по тегу: {e}")
            
            # Вариант 2: Ищем любой кликабельный div/span с текстом
            if not button_clicked:
                try:
                    clickable_elements = self.driver.find_elements(By.CSS_SELECTOR, "div[onclick], span[onclick], [role='button'], .button, .btn, [class*='button'], [class*='btn']")
                    for elem in clickable_elements:
                        if elem.is_displayed():
                            logger.info(f"✅ Найден кликабельный элемент")
                            ActionChains(self.driver).move_to_element(elem).click().perform()
                            button_clicked = True
                            time.sleep(2)
                            break
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось найти кликабельный элемент: {e}")
            
            # Вариант 3: Ищем по координатам центра экрана (если ничего не нашли)
            if not button_clicked:
                try:
                    # Кликаем в центр экрана
                    logger.info("⚠️ Ничего не найдено, кликаю в центр экрана...")
                    ActionChains(self.driver).move_by_offset(960, 540).click().perform()
                    button_clicked = True
                    time.sleep(2)
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось кликнуть в центр: {e}")
            
            if button_clicked:
                logger.info("✅ Первый попап обработан")
                return True
            else:
                logger.warning("⚠️ Не удалось обработать первый попап")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка при обработке первого попапа: {e}")
            try:
                self.driver.save_screenshot("debug_first_popup_error.png")
            except:
                pass
            return False
    
    def click_start_button(self) -> bool:
        """Кликает по кнопке 'НАЖМИТЕ ЧТОБЫ НАЧАТЬ'"""
        try:
            logger.info("🔍 Ищу кнопку 'НАЖМИТЕ ЧТОБЫ НАЧАТЬ'...")
            
            # Делаем скриншот перед поиском
            try:
                self.driver.save_screenshot("debug_step2_before_start.png")
            except:
                pass
            
            # Ждем появления кнопки (до 15 секунд)
            button_found = False
            
            # Вариант 1: По тексту
            try:
                start_button = WebDriverWait(self.driver, 15).until(
                    EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'НАЖМИТЕ') and contains(text(), 'НАЧАТЬ')]"))
                )
                logger.info("✅ Кнопка найдена по тексту")
                button_found = True
            except TimeoutException:
                logger.warning("⚠️ Кнопка не найдена по тексту")
            
            # Вариант 2: По любому элементу с большим текстом
            if not button_found:
                try:
                    all_elements = self.driver.find_elements(By.TAG_NAME, "*")
                    for elem in all_elements:
                        try:
                            text = elem.text.strip()
                            if 'НАЖМИТЕ' in text or 'НАЧАТЬ' in text:
                                if elem.is_displayed() and elem.is_enabled():
                                    logger.info(f"✅ Найден элемент с текстом: '{text[:50]}'")
                                    start_button = elem
                                    button_found = True
                                    break
                        except:
                            continue
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось найти по тексту: {e}")
            
            # Вариант 3: По CSS селекторам
            if not button_found:
                try:
                    selectors = ["button", ".start-button", "[class*='start']", "[class*='begin']", ".btn", "[role='button']"]
                    for selector in selectors:
                        try:
                            elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                            for elem in elements:
                                if elem.is_displayed() and elem.is_enabled():
                                    text = elem.text.strip()
                                    if len(text) > 5:
                                        logger.info(f"✅ Найден элемент по CSS: '{text}'")
                                        start_button = elem
                                        button_found = True
                                        break
                            if button_found:
                                break
                        except:
                            continue
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось найти по CSS: {e}")
            
            if button_found:
                # Кликаем по кнопке
                ActionChains(self.driver).move_to_element(start_button).click().perform()
                logger.info("✅ Клик по кнопке старта выполнен")
                
                # Ждем загрузки основного интерфейса
                time.sleep(5)
                
                # Делаем скриншот после клика
                try:
                    self.driver.save_screenshot("debug_step3_after_start.png")
                except:
                    pass
                
                # Проверяем, загрузился ли список участников
                try:
                    WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".item, .participant, [class*='participant']"))
                    )
                    logger.info("✅ Интерфейс со стримерами загружен")
                    return True
                except TimeoutException:
                    logger.warning("⚠️ Интерфейс не загрузился после клика")
                    return False
            else:
                # Кнопка не найдена - возможно уже нажата
                logger.warning("⚠️ Кнопка старта не найдена, проверяю наличие интерфейса...")
                
                try:
                    WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".item"))
                    )
                    logger.info("✅ Интерфейс уже загружен")
                    return True
                except:
                    logger.error("❌ Интерфейс не загружен")
                    self.driver.save_screenshot("debug_no_interface.png")
                    return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка при клике по кнопке старта: {e}")
            try:
                self.driver.save_screenshot("debug_start_error.png")
            except:
                pass
            return False
    
    def load_website(self) -> bool:
        """Полная загрузка сайта с обработкой всех попапов"""
        try:
            logger.info("🌐 Загружаю сайт...")
            self.driver.get(self.url)
            time.sleep(3)  # Ждем загрузки первой страницы
            
            # ШАГ 1: Обрабатываем первый попап (письмо)
            logger.info("📧 Шаг 1: Обрабатываю первый попап...")
            if not self.click_first_popup():
                logger.warning("⚠️ Первый попап не обработан, продолжаю...")
            
            time.sleep(2)  # Небольшая пауза между кликами
            
            # ШАГ 2: Кликаем по кнопке "НАЖМИТЕ ЧТОБЫ НАЧАТЬ"
            logger.info("🚀 Шаг 2: Кликаю по кнопке старта...")
            if not self.click_start_button():
                logger.error("❌ Не удалось загрузить основной интерфейс")
                return False
            
            logger.info("✅ Сайт полностью загружен!")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка при загрузке сайта: {e}")
            try:
                self.driver.save_screenshot("debug_load_error.png")
            except:
                pass
            return False
    
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
        """Получает данные всех участников с сайта"""
        try:
            # Загружаем сайт с обработкой всех попапов
            if not self.load_website():
                logger.error("❌ Не удалось загрузить сайт")
                return {}
            
            participants = {}
            
            # Получаем всех участников из списка слева
            participant_items = self.driver.find_elements(By.CSS_SELECTOR, ".item")
            logger.info(f"📊 Найдено участников: {len(participant_items)}")
            
            for item in participant_items:
                try:
                    position_elem = item.find_element(By.CSS_SELECTOR, ".position")
                    name_elem = item.find_element(By.CSS_SELECTOR, ".name")
                    points_elem = item.find_element(By.CSS_SELECTOR, ".points")
                    
                    position = int(position_elem.text.strip())
                    name = name_elem.text.strip()
                    points = points_elem.text.strip()
                    
                    is_selected = "selected" in item.get_attribute("class")
                    
                    participants[name] = {
                        'position': position,
                        'points': points,
                        'selected': is_selected,
                        'timestamp': time.time()
                    }
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось распарсить участника: {e}")
                    continue
            
            # Получаем текущее действие активного участника
            try:
                main_content = self.driver.find_element(By.CSS_SELECTOR, ".main-content")
                game_title_text = main_content.find_element(By.CSS_SELECTOR, ".game-title-text")
                action_text = game_title_text.text.strip()
                
                participants['_current_action'] = {
                    'action': action_text,
                    'timestamp': time.time()
                }
                logger.info(f"⚡ Текущее действие: {action_text}")
                
            except Exception as e:
                logger.warning(f"⚠️ Не удалось получить текущее действие: {e}")
            
            logger.info(f"✅ Получено данных: {len(participants)}")
            return participants
            
        except Exception as e:
            logger.error(f"❌ Ошибка при получении данных: {e}")
            try:
                self.driver.save_screenshot("debug_get_data.png")
            except:
                pass
            return {}
    
    def get_detailed_streamer_info(self, streamer_name: str) -> Optional[str]:
        """Получает ПОДРОБНУЮ информацию о конкретном стримере"""
        try:
            if streamer_name not in STREAMERS.values():
                return None
            
            # Кликаем по стримеру в списке
            participant_items = self.driver.find_elements(By.CSS_SELECTOR, ".item")
            
            for item in participant_items:
                try:
                    name_elem = item.find_element(By.CSS_SELECTOR, ".name")
                    if name_elem.text.strip() == streamer_name:
                        ActionChains(self.driver).move_to_element(item).click().perform()
                        time.sleep(2)
                        break
                except:
                    continue
            
            # Собираем базовую информацию
            streamer_info = None
            participant_items = self.driver.find_elements(By.CSS_SELECTOR, ".item")
            
            for item in participant_items:
                try:
                    name_elem = item.find_element(By.CSS_SELECTOR, ".name")
                    if name_elem.text.strip() == streamer_name:
                        position = item.find_element(By.CSS_SELECTOR, ".position").text.strip()
                        points = item.find_element(By.CSS_SELECTOR, ".points").text.strip()
                        is_selected = "selected" in item.get_attribute("class")
                        
                        streamer_info = {
                            'name': streamer_name,
                            'position': position,
                            'points': points,
                            'selected': is_selected
                        }
                        break
                except:
                    continue
            
            if not streamer_info:
                return None
            
            # Формируем сообщение
            message = f"👤 <b>{streamer_info['name']}</b>\n"
            message += f"📊 Позиция: {streamer_info['position']}\n"
            message += f"⭐ <b>Очки: {streamer_info['points']}</b>\n"
            
            # Если стример активен, получаем ДЕТАЛЬНУЮ информацию
            if streamer_info['selected']:
                try:
                    try:
                        game_cover = self.driver.find_element(By.CSS_SELECTOR, ".game-cover-img")
                        is_game = True
                    except:
                        is_game = False
                    
                    if is_game:
                        try:
                            game_title = self.driver.find_element(By.CSS_SELECTOR, ".game-title-text").text.strip()
                            message += f"\n🎮 <b>Игра:</b> {game_title}"
                        except:
                            pass
                        
                        try:
                            hltb_info = self.driver.find_element(By.CSS_SELECTOR, ".hltb-hours").text.strip()
                            message += f"\n⏱️ {hltb_info}"
                        except:
                            pass
                        
                        try:
                            timer = self.driver.find_element(By.CSS_SELECTOR, ".auction-timer-display").text.strip()
                            message += f"\n⏲️ Таймер: {timer}"
                        except:
                            pass
                        
                        try:
                            reward_items = self.driver.find_elements(By.CSS_SELECTOR, ".reward-item")
                            for reward in reward_items:
                                reward_value = reward.find_element(By.CSS_SELECTOR, ".reward-value").text.strip()
                                reward_label = reward.find_element(By.CSS_SELECTOR, ".reward-label").text.strip()
                                message += f"\n💰 {reward_value} ({reward_label})"
                        except:
                            pass
                        
                        try:
                            crown_result = self.driver.find_element(By.CSS_SELECTOR, ".crown-result").text.strip()
                            message += f"\n👑 Главный угонщик: {crown_result}"
                        except:
                            pass
                    else:
                        game_title = self.driver.find_element(By.CSS_SELECTOR, ".game-title-text").text.strip()
                        message += f"\n⚡ <b>Действие:</b> {game_title}"
                    
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось получить детали: {e}")
                    message += f"\n⚡ <b>Статус:</b> Активен"
            else:
                message += f"\n⚡ <b>Статус:</b> Не активен"
            
            return message
            
        except Exception as e:
            logger.error(f"❌ Ошибка при получении информации о стримере {streamer_name}: {e}")
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
                "/streamer [номер/имя] - ПОДРОБНАЯ информация о стримере\n"
                "/points - очки ВСЕХ участников\n"
                "/list - список всех участников\n"
                "/monitor - начать мониторинг изменений\n"
                "/stop - остановить бота\n\n"
                "💡 <b>Примеры:</b>\n"
                "/streamer 1 - инфо о Dunduk\n"
                "/streamer Flashko - инфо о Flashko\n\n"
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
                [(name, info) for name, info in data.items() if name != '_current_action'],
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
            
            info = self.get_detailed_streamer_info(streamer_name)
            
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
                if isinstance(info, dict) and info.get('selected'):
                    active_streamer = name
                    break
            
            action = "Неизвестно"
            if '_current_action' in data:
                action = data['_current_action'].get('action', 'Неизвестно')
            
            text = f"📊 <b>Текущий статус</b>\n\n"
            
            if active_streamer:
                active_points = data.get(active_streamer, {}).get('points', '0')
                text += f"🎯 <b>Активен:</b> {active_streamer}\n"
                text += f"⭐ <b>Очки:</b> {active_points}\n"
                text += f"⚡ <b>Действие:</b> {action}\n"
            else:
                text += "⚡ <b>Действие:</b> " + action
            
            text += f"\n\n⏰ {datetime.now().strftime('%H:%M:%S')}"
            
            await message.answer(text, parse_mode="HTML")
        
        @self.dp.message(Command("monitor"))
        async def cmd_monitor(message: types.Message):
            await message.answer("🔔 Мониторинг изменений активирован!\n\nБот будет присылать:\n• Изменения в очках\n• Смену активного стримера\n• Изменение действий\n• Смену позиций")
            asyncio.create_task(self.monitor_loop())
        
        @self.dp.message(Command("stop"))
        async def cmd_stop(message: types.Message):
            await message.answer("👋 Бот остановлен")
            self.driver.quit()
            await self.bot.close()
        
        @self.dp.message()
        async def handle_keyboard(message: types.Message):
            text = message.text.strip()
            
            for num, name in STREAMERS.items():
                if text == f"{num}. {name}" or text == name:
                    await message.answer(f"⏳ Загрузка информации о {name}...")
                    
                    info = self.get_detailed_streamer_info(name)
                    
                    if info:
                        await message.answer(info, parse_mode="HTML")
                    else:
                        await message.answer(f"❌ Не удалось получить информацию о {name}")
                    return
        
        logger.info("🚀 Бот запущен!")
        await self.dp.start_polling(self.bot)
    
    async def monitor_loop(self):
        logger.info("Запуск мониторинга...")
        
        logger.info("🔄 Инициализация: получаем текущее состояние сайта...")
        initial_data = await self.get_participants_data()
        
        if initial_data:
            self.previous_data = initial_data
            logger.info(f"✅ Начальное состояние запомнено ({len(initial_data)} участников)")
            logger.info("🔍 Теперь буду следить за изменениями...")
        else:
            logger.error("❌ Не удалось получить начальное состояние")
            return
        
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
        changes = []
        
        if '_current_action' in new_data and '_current_action' in old_data:
            old_action = old_data['_current_action'].get('action', '')
            new_action = new_data['_current_action'].get('action', '')
            
            if old_action != new_action:
                active_streamer = None
                for name, info in new_data.items():
                    if isinstance(info, dict) and info.get('selected'):
                        active_streamer = name
                        break
                
                changes.append(
                    f"🎯 <b>Новое действие</b>\n"
                    f"👤 Участник: {active_streamer or 'Неизвестно'}\n"
                    f"❌ Было: {old_action}\n"
                    f"✅ Стало: {new_action}"
                )
        
        points_changes = []
        position_changes = []
        
        for name, data in new_data.items():
            if name == '_current_action':
                continue
                
            if name in old_data:
                old_points = old_data[name].get('points', '0')
                new_points = data.get('points', '0')
                
                if old_points != new_points:
                    try:
                        old_points_int = int(old_points)
                        new_points_int = int(new_points)
                        diff = new_points_int - old_points_int
                        
                        if diff > 0:
                            arrow = "⬆️"
                            sign = "+"
                        elif diff < 0:
                            arrow = "⬇️"
                            sign = ""
                        else:
                            arrow = ""
                            sign = ""
                        
                        points_changes.append(
                            f"{arrow} <b>{name}</b>\n"
                            f"Очки: {old_points} → {new_points} ({sign}{diff})"
                        )
                    except:
                        points_changes.append(
                            f"⭐ <b>{name}</b>\n"
                            f"Очки: {old_points} → {new_points}"
                        )
                
                old_pos = old_data[name].get('position', 0)
                new_pos = data.get('position', 0)
                
                if old_pos != new_pos:
                    if new_pos < old_pos:
                        arrow = "⬆️"
                    else:
                        arrow = "⬇️"
                    
                    position_changes.append(
                        f"{arrow} <b>{name}</b>\n"
                        f"Позиция: {old_pos} → {new_pos}"
                    )
            
            if data.get('selected') and not old_data.get(name, {}).get('selected'):
                changes.append(f"🔥 <b>{name}</b> стал активным!")
        
        if points_changes:
            changes.append("💰 <b>Изменения в очках:</b>\n" + "\n".join(points_changes))
        
        if position_changes:
            changes.append("📊 <b>Изменения в позициях:</b>\n" + "\n".join(position_changes))
        
        return changes


async def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    CHAT_ID = os.getenv("CHAT_ID", "-1003268832776")
    
    if not BOT_TOKEN:
        logger.error("❌ Переменная окружения BOT_TOKEN не найдена!")
        logger.error("Убедитесь, что переменная BOT_TOKEN задана в настройках хоста")
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
