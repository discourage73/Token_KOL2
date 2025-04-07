import requests
import logging
import datetime
import time
import asyncio
import random
from typing import Dict, Any, Optional, Union, List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from telegram.error import TimedOut, NetworkError

# Импортируем модули проекта
import token_storage
from config import DEXSCREENER_API_URL, logger
from utils import process_token_data, format_message, format_number

# Добавляем счетчик запросов для защиты от блокировки API
api_request_count = 0
last_api_request_time = 0
API_REQUEST_LIMIT = 60  # Максимальное число запросов в минуту
API_COOLDOWN_TIME = 70  # Время ожидания после достижения лимита (в секундах)

async def get_token_info(
    query: str, 
    chat_id: int, 
    message_id: Optional[int] = None, 
    context: Optional[ContextTypes.DEFAULT_TYPE] = None
) -> Optional[Dict[str, Any]]:
    """Получает информацию о токене и отправляет или обновляет сообщение."""
    try:
        # Сообщаем в лог о запросе
        logger.info(f"Запрос информации о токене: {query}")
        
        # Используем DexScreener API для поиска по разным параметрам
        logger.info(f"Отправка запроса к DexScreener API: {DEXSCREENER_API_URL}?q={query}")
        response = requests.get(f"{DEXSCREENER_API_URL}?q={query}", timeout=20)
        
        logger.info(f"Получен ответ от API. Статус: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            pairs = data.get('pairs', [])
            
            logger.info(f"Получено {len(pairs)} пар для токена {query}")
            
            if not pairs:
                if context and chat_id:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"Не удалось найти информацию о токене '{query}'."
                    )
                return None
            
            # Берем первый результат как наиболее релевантный
            token_data = pairs[0]
            
            # Обрабатываем данные
            token_info = process_token_data(token_data)
            
            # Получаем начальные данные, если токен уже отслеживается
            initial_data = None
            send_growth_notification = False
            current_multiplier = 1
            
            # Получаем данные о токене из хранилища
            stored_data = token_storage.get_token_data(query)
            
            if stored_data:
                initial_data = stored_data.get('initial_data')
                
                # Проверяем значительный рост, если есть начальные данные
                if (initial_data and 'raw_market_cap' in initial_data and 
                    initial_data['raw_market_cap'] and token_info['raw_market_cap']):
                    initial_mcap = initial_data['raw_market_cap']
                    current_mcap = token_info['raw_market_cap']
                    
                    # Вычисляем множитель
                    if initial_mcap > 0:
                        multiplier = current_mcap / initial_mcap
                        current_multiplier = int(multiplier)
                        
                        # Проверяем, был ли уже отправлен алерт для данного множителя
                        last_alert_multiplier = stored_data.get('last_alert_multiplier', 1)
                        
                        # Важно! Добавим подробный лог для отладки
                        logger.info(f"Токен {query}: текущий множитель = {multiplier}, целый множитель = {current_multiplier}, последний алерт = {last_alert_multiplier}")
                        
                        # Если текущий множитель >= 2 и превышает предыдущий алерт
                        if current_multiplier >= 2 and current_multiplier > last_alert_multiplier:
                            send_growth_notification = True
                            logger.info(f"ТРИГГЕР АЛЕРТА: Токен {query} достиг множителя x{current_multiplier}")
            else:
                # Сохраняем начальные данные для нового токена
                current_time = datetime.datetime.now().strftime("%H:%M:%S")
                initial_data = {
                    'time': current_time,
                    'market_cap': token_info['market_cap'],
                    'raw_market_cap': token_info['raw_market_cap']
                }
                logger.info(f"Новый токен {query} добавлен с начальным Market Cap: {token_info['market_cap']}")
            
            # Форматируем сообщение
            message = format_message(token_info, initial_data)
            
            # Создаем кнопку обновления
            keyboard = [[InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh:{query}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Если есть context и chat_id, отправляем или обновляем сообщение
            if context and chat_id:
                if message_id:
                    # Обновляем существующее сообщение
                    try:
                        logger.info(f"Обновление сообщения для токена {query}")
                        await context.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=message,
                            parse_mode=ParseMode.MARKDOWN,
                            reply_markup=reply_markup,
                            disable_web_page_preview=True
                        )
                        logger.info(f"Сообщение для токена {query} успешно обновлено")
                    except Exception as e:
                        if "Message is not modified" not in str(e):
                            logger.error(f"Ошибка при обновлении сообщения: {e}")
                            raise e
                        else:
                            logger.info("Сообщение не изменилось, обновление не требуется")
                else:
                    # Отправляем новое сообщение
                    logger.info(f"Отправка нового сообщения для токена {query}")
                    try:
                        sent_msg = await context.bot.send_message(
                            chat_id=chat_id,
                            text=message,
                            parse_mode=ParseMode.MARKDOWN,
                            reply_markup=reply_markup,
                            disable_web_page_preview=True
                        )
                        
                        logger.info(f"Новое сообщение для токена {query} успешно отправлено")
                        
                        # Сохраняем данные о токене в хранилище
                        token_data_to_store = {
                            'last_update_time': time.time(),
                            'message_id': sent_msg.message_id,
                            'chat_id': sent_msg.chat_id,
                            'initial_data': initial_data,
                            'token_info': token_info,  # Сохраняем информацию о токене
                            'last_alert_multiplier': 1,  # Добавляем отслеживание последнего алерта
                            'added_time': time.time()  # Время добавления токена
                        }
                        token_storage.store_token_data(query, token_data_to_store)
                    except Exception as e:
                        logger.error(f"Ошибка при отправке нового сообщения: {e}")
                        raise e
                
                # Обновляем информацию о токене в хранилище
                if stored_data:
                    token_storage.update_token_field(query, 'token_info', token_info)
                    logger.info(f"Обновлена информация о токене {query} в хранилище")
                
                # Обновляем ATH маркет кап, если текущее значение выше
                if token_info['raw_market_cap']:
                    ath_updated = token_storage.update_token_ath(query, token_info['raw_market_cap'])
                    logger.info(f"ATH для токена {query}: {'обновлен' if ath_updated else 'не изменился'}, текущий ATH: {token_storage.get_token_data(query).get('ath_market_cap', 0)}")
                
                # Отправляем уведомление о значительном росте, если необходимо
                if send_growth_notification:
                    try:
                        logger.info(f"Отправка уведомления о росте для токена {query}")
                        growth_message = (
                            f"🚀 *ИКСАНУЛ!* 🚀\n\n"
                            f"Токен *{token_info['ticker']}* вырос в *{current_multiplier}x* от начального значения!\n\n"
                            f"💰 Текущий Market Cap: {token_info['market_cap']}"
                        )
                        
                        # Проверяем, есть ли сообщение для ответа
                        reply_to_message_id = None
                        if message_id:
                            reply_to_message_id = message_id
                        
                        sent = await context.bot.send_message(
                            chat_id=chat_id,
                            text=growth_message,
                            parse_mode=ParseMode.MARKDOWN,
                            disable_web_page_preview=True,
                            reply_to_message_id=reply_to_message_id
                        )
                        
                        # Обновляем последний отправленный алерт только если сообщение было успешно отправлено
                        if sent:
                            token_storage.update_token_field(query, 'last_alert_multiplier', current_multiplier)
                            logger.info(f"Успешно отправлено уведомление о росте токена {token_info['ticker']} в {current_multiplier}x")
                    except Exception as e:
                        logger.error(f"Ошибка при отправке уведомления о росте: {e}")
            
            return token_info
        
        else:
            if context and chat_id:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"Ошибка при запросе к API. Код: {response.status_code}."
                )
            return None
    
    except Exception as e:
        logger.error(f"Ошибка при получении данных о токене: {e}")
        if context and chat_id:
            await context.bot.send_message(
                chat_id=chat_id,
                text="Произошла ошибка при получении данных."
            )
        return None

async def check_market_cap_only(
    query: str,
    chat_id: int,
    context: Optional[ContextTypes.DEFAULT_TYPE] = None
) -> Optional[Dict[str, Any]]:
    """Проверяет только Market Cap токена без обновления остальных данных."""
    global api_request_count, last_api_request_time
    
    try:
        current_time = time.time()
        
        # Проверка лимита API запросов
        if current_time - last_api_request_time >= 60:  # Сбрасываем счетчик каждую минуту
            api_request_count = 0
            last_api_request_time = current_time
        
        if api_request_count >= API_REQUEST_LIMIT:
            logger.warning(f"Достигнут лимит API запросов ({API_REQUEST_LIMIT}/мин). Пауза {API_COOLDOWN_TIME} секунд.")
            await asyncio.sleep(API_COOLDOWN_TIME)
            api_request_count = 0
            last_api_request_time = time.time()
        
        # Получаем данные о токене из хранилища
        stored_data = token_storage.get_token_data(query)
        if not stored_data:
            logger.warning(f"Не найдены данные о токене {query} для обновления Market Cap")
            return None
        
        # Добавляем небольшую случайную задержку для распределения запросов
        await asyncio.sleep(random.uniform(0.1, 0.5))
        
        logger.info(f"Запрос обновления Market Cap для токена {query}")
        
        # Отправляем запрос к API
        response = requests.get(f"{DEXSCREENER_API_URL}?q={query}", timeout=20)
        api_request_count += 1
        
        if response.status_code == 200:
            data = response.json()
            pairs = data.get('pairs', [])
            
            if not pairs:
                logger.warning(f"Не удалось получить данные о токене {query} для обновления Market Cap")
                return None
            
            # Берем только Market Cap из первого результата
            token_data = pairs[0]
            market_cap = token_data.get('fdv')
            
            if not market_cap:
                logger.warning(f"Не удалось получить Market Cap для токена {query}")
                return None
            
            # Обновляем Market Cap в token_info
            if 'token_info' not in stored_data:
                # Если token_info отсутствует, создаем базовую структуру
                stored_data['token_info'] = {'raw_market_cap': market_cap}
            else:
                stored_data['token_info']['raw_market_cap'] = market_cap
            
            # Обновляем данные в хранилище
            token_storage.update_token_field(query, 'token_info', stored_data['token_info'])
            logger.info(f"Обновлен Market Cap для токена {query}: {format_number(market_cap)}")
            
            # Обновляем ATH, если текущее значение выше
            ath_updated = token_storage.update_token_ath(query, market_cap)
            logger.info(f"ATH для токена {query}: {'обновлен' if ath_updated else 'не изменился'}, текущий ATH: {token_storage.get_token_data(query).get('ath_market_cap', 0)}")
            
            # Проверяем значительный рост, если есть начальные данные
            initial_data = stored_data.get('initial_data')
            send_growth_notification = False
            current_multiplier = 1
            
            if (initial_data and 'raw_market_cap' in initial_data and 
                initial_data['raw_market_cap'] and market_cap):
                initial_mcap = initial_data['raw_market_cap']
                
                # Вычисляем множитель
                if initial_mcap > 0:
                    multiplier = market_cap / initial_mcap
                    current_multiplier = int(multiplier)
                    
                    # Проверяем, был ли уже отправлен алерт для данного множителя
                    last_alert_multiplier = stored_data.get('last_alert_multiplier', 1)
                    
                    # Важно! Добавим подробный лог для отладки
                    logger.info(f"Токен {query}: текущий множитель = {multiplier}, целый множитель = {current_multiplier}, последний алерт = {last_alert_multiplier}")
                    
                    # Если текущий множитель >= 2 и превышает предыдущий алерт
                    if current_multiplier >= 2 and current_multiplier > last_alert_multiplier:
                        send_growth_notification = True
                        logger.info(f"ТРИГГЕР АЛЕРТА: Токен {query} достиг множителя x{current_multiplier}")
            
            # Отправляем уведомление о значительном росте, если необходимо
            if send_growth_notification and context and chat_id:
                try:
                    logger.info(f"Отправка уведомления о росте для токена {query}")
                    
                    # Получаем тикер из stored_data
                    ticker = query
                    if 'token_info' in stored_data and 'ticker' in stored_data['token_info']:
                        ticker = stored_data['token_info']['ticker']
                    
                    growth_message = (
                        f"🚀 *ИКСАНУЛ!* 🚀\n\n"
                        f"Токен *{ticker}* вырос в *{current_multiplier}x* от начального значения!\n\n"
                        f"💰 Текущий Market Cap: {format_number(market_cap)}"
                    )
                    
                    # Получаем ID сообщения для ответа, если есть
                    message_id = stored_data.get('message_id')
                    
                    sent = await context.bot.send_message(
                        chat_id=chat_id,
                        text=growth_message,
                        parse_mode=ParseMode.MARKDOWN,
                        disable_web_page_preview=True,
                        reply_to_message_id=message_id
                    )
                    
                    # Обновляем последний отправленный алерт
                    if sent:
                        token_storage.update_token_field(query, 'last_alert_multiplier', current_multiplier)
                        logger.info(f"Успешно отправлено уведомление о росте токена {ticker} в {current_multiplier}x")
                except Exception as e:
                    logger.error(f"Ошибка при отправке уведомления о росте: {e}")
            
            return {'market_cap': format_number(market_cap), 'raw_market_cap': market_cap}
        
        else:
            logger.warning(f"Ошибка при запросе к API для токена {query}. Код: {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"Ошибка при проверке Market Cap для токена {query}: {e}")
        return None

async def process_token_address(address: str, chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает адрес токена, полученный от внешнего источника."""
    logger.info(f"Обработка адреса токена: {address}")
    
    # Проверяем, есть ли уже данные об этом токене
    stored_data = token_storage.get_token_data(address)
    
    if stored_data:
        # Обновляем существующее сообщение
        logger.info(f"Найдены сохраненные данные о токене {address}")
        message_id = stored_data.get('message_id')
        logger.info(f"ID сообщения: {message_id}")
        result = await get_token_info(address, chat_id, message_id, context)
        if result:
            logger.info(f"Обновление информации о токене {address} успешно выполнено")
        else:
            logger.warning(f"Обновление информации о токене {address} не удалось")
    else:
        # Отправляем новое сообщение
        logger.info(f"Сохраненных данных о токене {address} не найдено, отправляем новое сообщение")
        result = await get_token_info(address, chat_id, None, context)
        if result:
            logger.info(f"Отправка информации о новом токене {address} успешно выполнена")
        else:
            logger.warning(f"Отправка информации о новом токене {address} не удалась")

async def check_all_tokens_growth(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Проверяет рост маркет капа всех отслеживаемых токенов."""
    logger.info("Начало автоматической проверки всех токенов")
    
    # Обновляем время последней автоматической проверки
    token_storage.update_last_auto_check_time()
    
    # Очищаем устаревшие токены перед проверкой
    expired_tokens = token_storage.clean_expired_tokens()
    if expired_tokens:
        logger.info(f"Удалено {len(expired_tokens)} устаревших токенов")
    
    # Получаем все отслеживаемые токены
    all_tokens = token_storage.get_all_tokens()
    
    for query, token_data in all_tokens.items():
        try:
            chat_id = token_data.get('chat_id')
            message_id = token_data.get('message_id')
            
            if not chat_id or not message_id:
                logger.warning(f"Недостаточно данных для обновления токена {query}")
                continue
            
            # Обновляем информацию о токене
            logger.info(f"Автоматическая проверка токена {query}")
            result = await get_token_info(query, chat_id, message_id, context)
            
            if result:
                logger.info(f"Автоматическое обновление токена {query} успешно выполнено")
            else:
                logger.warning(f"Автоматическое обновление токена {query} не удалось")
                
            # Чтобы не перегружать API, делаем небольшую паузу между запросами
            await asyncio.sleep(2)
            
        except Exception as e:
            logger.error(f"Ошибка при автоматической проверке токена {query}: {e}")

async def check_all_market_caps(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Проверяет Market Cap всех отслеживаемых токенов."""
    logger.info("Начало автоматической проверки Market Cap всех токенов")
    
    # Обновляем время последней автоматической проверки
    token_storage.update_last_auto_check_time()
    
    # Очищаем устаревшие токены перед проверкой
    expired_tokens = token_storage.clean_expired_tokens()
    if expired_tokens:
        logger.info(f"Удалено {len(expired_tokens)} устаревших токенов")
    
    # Получаем все отслеживаемые токены
    all_tokens = token_storage.get_all_tokens()
    
    for query, token_data in all_tokens.items():
        try:
            chat_id = token_data.get('chat_id')
            
            if not chat_id:
                logger.warning(f"Недостаточно данных для обновления токена {query}")
                continue
            
            # Обновляем только Market Cap
            logger.info(f"Автоматическая проверка Market Cap токена {query}")
            result = await check_market_cap_only(query, chat_id, context)
            
            if result:
                logger.info(f"Автоматическое обновление Market Cap токена {query} успешно выполнено: {result['market_cap']}")
            else:
                logger.warning(f"Автоматическое обновление Market Cap токена {query} не удалось")
                
            # Небольшая пауза между запросами для снижения нагрузки на API
            await asyncio.sleep(random.uniform(1.0, 2.0))
            
        except Exception as e:
            logger.error(f"Ошибка при автоматической проверке Market Cap токена {query}: {e}")
            await asyncio.sleep(1.0)  # Пауза в случае ошибки