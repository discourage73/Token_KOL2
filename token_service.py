import requests
import logging
import datetime
import time
import asyncio
import random
import json
import os
import pandas as pd
from typing import Dict, Any, Optional, Union, List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from telegram.error import TimedOut, NetworkError

# Импортируем модули проекта
import token_storage
from config import DEXSCREENER_API_URL, logger
from utils import process_token_data, format_message, format_number, format_growth_message

# Параметры API
API_REQUEST_LIMIT = 60  # Максимальное число запросов в минуту
API_COOLDOWN_TIME = 70  # Время ожидания после достижения лимита (в секундах)
api_request_count = 0
last_api_request_time = 0

# Настройки для мониторинга
MONITOR_INTERVAL = 10  # Интервал проверки маркет капа в секундах

async def get_token_info(
    query: str, 
    chat_id: int, 
    message_id: Optional[int] = None, 
    context: Optional[ContextTypes.DEFAULT_TYPE] = None
) -> Optional[Dict[str, Any]]:
    """Получает информацию о токене и отправляет или обновляет сообщение."""
    try:
        logger.info(f"Запрос информации о токене: {query}")
        
        response = requests.get(f"{DEXSCREENER_API_URL}?q={query}", timeout=20)
        logger.info(f"Получен ответ от API. Статус: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            pairs = data.get('pairs', [])
            
            if not pairs:
                if context and chat_id:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"Не удалось найти информацию о токене '{query}'."
                    )
                return None
            
            # Берем первый результат как наиболее релевантный
            token_data = pairs[0]
            raw_api_data = token_data
            
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
                        
                        logger.info(f"Токен {query}: текущий множитель = {multiplier}, целый множитель = {current_multiplier}")
                        
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
                # Логика отправки/обновления сообщения и сохранения данных
                if message_id:
                    try:
                        await context.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=message,
                            parse_mode=ParseMode.MARKDOWN,
                            reply_markup=reply_markup,
                            disable_web_page_preview=True
                        )
                    except Exception as e:
                        if "Message is not modified" not in str(e):
                            logger.error(f"Ошибка при обновлении сообщения: {e}")
                else:
                    try:
                        sent_msg = await context.bot.send_message(
                            chat_id=chat_id,
                            text=message,
                            parse_mode=ParseMode.MARKDOWN,
                            reply_markup=reply_markup,
                            disable_web_page_preview=True
                        )
                        
                        # Сохраняем данные о токене в хранилище
                        token_data_to_store = {
                            'last_update_time': time.time(),
                            'message_id': sent_msg.message_id,
                            'chat_id': sent_msg.chat_id,
                            'initial_data': initial_data,
                            'token_info': token_info,
                            'last_alert_multiplier': 1,
                            'added_time': time.time(),
                            'raw_api_data': raw_api_data
                        }
                        
                        token_storage.store_token_data(query, token_data_to_store)
                    except Exception as e:
                        logger.error(f"Ошибка при отправке нового сообщения: {e}")
                
                # Обработка роста и уведомлений
                if send_growth_notification:
                    try:
                        # Используем функцию для формирования сообщения о росте
                        growth_message = format_growth_message(token_info['ticker'], current_multiplier, token_info['market_cap'])
                        
                        sent = await context.bot.send_message(
                            chat_id=chat_id,
                            text=growth_message,
                            parse_mode=ParseMode.MARKDOWN,
                            disable_web_page_preview=True,
                            reply_to_message_id=message_id
                        )
                        
                        if sent:
                            token_storage.update_token_field(query, 'last_alert_multiplier', current_multiplier)
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

async def process_token_address(address: str, chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает адрес токена, полученный от внешнего источника."""
    logger.info(f"Обработка адреса токена: {address}")
    
    try:
        # Уведомляем пользователя о начале обработки
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=f"Получен новый контракт: {address}\nИщу информацию о токене..."
        )
        
        # Проверяем, есть ли уже данные об этом токене
        stored_data = token_storage.get_token_data(address)
        
        if stored_data:
            # Обновляем существующее сообщение
            message_id = stored_data.get('message_id')
            
            # Используем функцию get_token_info из test_bot4.py вместо original_get_token_info
            # Импортируем её динамически, чтобы избежать циклических импортов
            from test_bot4 import get_token_info as enhanced_get_token_info
            result = await enhanced_get_token_info(address, chat_id, message_id, context)
            
            logger.info(f"Обновление информации о токене {address}: {'успешно' if result else 'не удалось'}")
        else:
            # Отправляем новое сообщение
            from test_bot4 import get_token_info as enhanced_get_token_info
            result = await enhanced_get_token_info(address, chat_id, None, context)
            
            logger.info(f"Отправка информации о новом токене {address}: {'успешно' if result else 'не удалось'}")
        
        # Удаляем сообщение о поиске
        try:
            await msg.delete()
        except Exception as e:
            logger.error(f"Ошибка при удалении сообщения о поиске: {e}")
    
    except Exception as e:
        logger.error(f"Ошибка при обработке адреса токена: {e}")
        import traceback
        logger.error(traceback.format_exc())
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"Ошибка при обработке контракта {address}: {str(e)}"
            )
        except:
            pass

async def monitor_token_market_caps(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Отслеживает маркет кап токенов и проверяет на мультипликаторы x2, x3 и т.д.
    Функция предназначена для использования в планировщике задач.
    Интервал запуска: MONITOR_INTERVAL секунд (10 сек.)
    """
    try:
        # Получаем все активные токены
        active_tokens = token_storage.get_active_tokens()
        
        if not active_tokens:
            logger.info("Нет активных токенов для мониторинга маркет капа")
            return
            
        logger.info(f"Запущен мониторинг маркет капа, всего токенов: {len(active_tokens)}")
        
        # Для каждого токена обновляем маркет кап и проверяем рост
        for query, token_data in active_tokens.items():
            try:
                chat_id = token_data.get('chat_id')
                message_id = token_data.get('message_id')
                
                if not chat_id:
                    continue
                    
                # Проверяем, не слишком ли часто обновляем токен
                last_update_time = token_data.get('last_update_time', 0)
                current_time = time.time()
                
                # Пропускаем токены, которые были обновлены менее 5 секунд назад
                if current_time - last_update_time < 5:
                    continue
                
                # Получаем последние данные о маркет капе
                result = await check_market_cap_growth(query, chat_id, message_id, context)
                
                if result:
                    logger.info(f"Мониторинг токена {query}: MC={result.get('market_cap')}, Multiplier={result.get('multiplier', 1)}")
                    
                    # Проверяем на мультипликатор и отправляем уведомление если нужно
                    send_notification = result.get('send_notification', False)
                    current_multiplier = result.get('current_multiplier', 1)
                    
                    if send_notification and current_multiplier >= 2:
                        # Отправляем уведомление о росте
                        token_info = token_data.get('token_info', {})
                        ticker = token_info.get('ticker', 'Неизвестно')
                        market_cap = result.get('market_cap', 'Неизвестно')
                        
                        # Используем функцию для формирования сообщения о росте
                        growth_message = format_growth_message(ticker, current_multiplier, market_cap)
                        
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=growth_message,
                            parse_mode=ParseMode.MARKDOWN,
                            disable_web_page_preview=True,
                            reply_to_message_id=message_id
                        )
                        
                        # Обновляем последний алерт
                        token_storage.update_token_field(query, 'last_alert_multiplier', current_multiplier)
                        logger.info(f"Отправлено уведомление о росте токена {ticker} до x{current_multiplier}")
                
                # Добавляем небольшую паузу между запросами к API
                await asyncio.sleep(random.uniform(0.5, 1.0))
                
            except Exception as e:
                logger.error(f"Ошибка при мониторинге токена {query}: {e}")
                continue
                
    except Exception as e:
        logger.error(f"Ошибка в задаче мониторинга маркет капа: {e}")
        import traceback
        logger.error(traceback.format_exc())

async def check_all_market_caps(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Проверяет Market Cap всех отслеживаемых токенов.
    Не отправляет регулярных сообщений, только уведомления о росте.
    """
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
            message_id = token_data.get('message_id')
            
            if not chat_id:
                logger.warning(f"Недостаточно данных для обновления токена {query}")
                continue
            
            # Проверяем маркет кап и рост токена
            logger.info(f"Автоматическая проверка Market Cap токена {query}")
            result = await check_market_cap_growth(query, chat_id, message_id, context)
            
            if result:
                # Проверяем, нужно ли отправить уведомление о росте
                send_notification = result.get('send_notification', False)
                current_multiplier = result.get('current_multiplier', 1)
                
                if send_notification and current_multiplier >= 2:
                    # Отправляем уведомление о росте
                    token_info = token_data.get('token_info', {})
                    ticker = token_info.get('ticker', 'Неизвестно')
                    market_cap = result.get('market_cap', 'Неизвестно')
                    
                    # Используем функцию для формирования сообщения о росте
                    growth_message = format_growth_message(ticker, current_multiplier, market_cap)
                    
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=growth_message,
                        parse_mode=ParseMode.MARKDOWN,
                        disable_web_page_preview=True,
                        reply_to_message_id=message_id
                    )
                    
                    # Обновляем последний алерт
                    token_storage.update_token_field(query, 'last_alert_multiplier', current_multiplier)
                    logger.info(f"Отправлено уведомление о росте токена {ticker} до x{current_multiplier}")
                
                logger.info(f"Автоматическое обновление Market Cap токена {query} успешно выполнено: {result['market_cap']}")
            else:
                logger.warning(f"Автоматическое обновление Market Cap токена {query} не удалось")
                
            # Небольшая пауза между запросами для снижения нагрузки на API
            await asyncio.sleep(random.uniform(0.5, 1.0))
            
        except Exception as e:
            logger.error(f"Ошибка при автоматической проверке Market Cap токена {query}: {e}")
            await asyncio.sleep(0.5)  # Короткая пауза в случае ошибки

async def check_market_cap_growth(
    query: str,
    chat_id: int,
    message_id: Optional[int] = None,
    context: Optional[ContextTypes.DEFAULT_TYPE] = None
) -> Optional[Dict[str, Any]]:
    """
    Проверяет маркет кап токена и определяет, достиг ли он нового мультипликатора.
    Возвращает информацию о текущем маркет капе и флаг для отправки уведомления.
    """
    try:
        # Получаем данные о токене из хранилища
        stored_data = token_storage.get_token_data(query)
        if not stored_data:
            logger.warning(f"Не найдены данные о токене {query} для проверки роста")
            return None
        
        # Получаем последние данные о маркет капе с повторными попытками
        max_retries = 2  # Уменьшаем количество попыток для ускорения
        response = None
        
        for attempt in range(max_retries):
            try:
                response = requests.get(f"{DEXSCREENER_API_URL}?q={query}", timeout=7)  # Уменьшаем таймаут
                break
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Таймаут при запросе к API ({attempt+1}/{max_retries}): {e}")
                    await asyncio.sleep(1)  # Короткая пауза перед повторной попыткой
                else:
                    logger.error(f"Не удалось подключиться к API после {max_retries} попыток: {e}")
                    return None
        
        if not response:
            return None
        
        if response.status_code == 200:
            data = response.json()
            pairs = data.get('pairs', [])
            
            if not pairs:
                logger.warning(f"API не вернуло данные о парах для токена {query}")
                return None
            
            # Берем первый результат
            token_data = pairs[0]
            
            # Получаем и обновляем market cap
            market_cap = token_data.get('fdv')
            raw_market_cap = market_cap  # Сохраняем исходное значение
            market_cap_formatted = format_number(market_cap)
            
            # Обновляем только поле market_cap в хранилище
            if 'token_info' in stored_data:
                stored_data['token_info']['market_cap'] = market_cap_formatted
                stored_data['token_info']['raw_market_cap'] = raw_market_cap
                
                # Обновляем время последнего обновления
                stored_data['last_update_time'] = time.time()
                
                # Обновляем данные в хранилище
                token_storage.store_token_data(query, stored_data)
                
                # Обновляем ATH, если текущее значение выше
                if raw_market_cap:
                    token_storage.update_token_ath(query, raw_market_cap)
                
                # Проверяем, достиг ли токен нового множителя роста
                send_notification = False
                current_multiplier = 1
                
                initial_data = stored_data.get('initial_data', {})
                initial_mcap = initial_data.get('raw_market_cap', 0)
                
                if initial_mcap and initial_mcap > 0 and raw_market_cap:
                    # Вычисляем множитель
                    multiplier = raw_market_cap / initial_mcap
                    current_multiplier = int(multiplier)  # Округляем до целого числа
                    
                    # Проверяем, был ли уже отправлен алерт для данного множителя
                    last_alert_multiplier = stored_data.get('last_alert_multiplier', 1)
                    
                    # Если текущий множитель >= 2 и превышает предыдущий алерт
                    if current_multiplier >= 2 and current_multiplier > last_alert_multiplier:
                        send_notification = True
                        logger.info(f"Обнаружен новый множитель для токена {query}: x{current_multiplier} (предыдущий: x{last_alert_multiplier})")
                
                return {
                    'market_cap': market_cap_formatted, 
                    'raw_market_cap': raw_market_cap,
                    'multiplier': multiplier if 'multiplier' in locals() else 1,
                    'current_multiplier': current_multiplier,
                    'send_notification': send_notification
                }
            else:
                logger.warning(f"В хранилище нет поля token_info для токена {query}")
                return None
        else:
            logger.warning(f"API вернуло ошибку {response.status_code} для токена {query}")
            return None
            
    except Exception as e:
        logger.error(f"Ошибка при проверке роста маркет капа для токена {query}: {e}")
        return None

async def send_token_stats(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Отправляет статистику по токенам за последние 12 часов.
    Эта функция запускается по расписанию.
    """
    try:
        # Улучшенное логирование для отладки
        logger.info("=== НАЧАЛО ФОРМИРОВАНИЯ СТАТИСТИКИ ПО ТОКЕНАМ ===")
        
        # Получаем все токены
        all_tokens = token_storage.get_all_tokens(include_hidden=True)
        logger.info(f"Загружено токенов для анализа: {len(all_tokens)}")
        
        if not all_tokens:
            logger.info("Нет токенов для формирования статистики")
            return
        
        # Текущее время
        current_time = time.time()
        logger.info(f"Текущее время: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Время 12 часов назад
        time_12h_ago = current_time - (12 * 60 * 60)
        logger.info(f"Время 12 часов назад: {datetime.datetime.fromtimestamp(time_12h_ago).strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Счетчики для статистики
        total_tokens = 0
        tokens_1_5x = 0
        tokens_2x = 0
        tokens_5x = 0
        
        # Список токенов для подробного логирования
        analyzed_tokens = []
        
        # Проверяем каждый токен
        for query, data in all_tokens.items():
            # Проверяем, был ли токен добавлен в течение последних 12 часов
            added_time = data.get('added_time', 0)
            
            if not added_time:
                logger.info(f"Токен {query} не имеет времени добавления, пропускаем")
                continue
                
            # Логируем время добавления токена
            token_added_time = datetime.datetime.fromtimestamp(added_time).strftime('%Y-%m-%d %H:%M:%S')
            logger.info(f"Токен {query} добавлен: {token_added_time}")
            
            if added_time < time_12h_ago:
                logger.info(f"Токен {query} добавлен более 12 часов назад, пропускаем")
                continue
                
            # Получаем начальный маркет кап
            initial_mcap = 0
            if 'initial_data' in data and 'raw_market_cap' in data['initial_data']:
                initial_mcap = data['initial_data'].get('raw_market_cap', 0)
            
            # Берем ATH маркет кап вместо текущего
            ath_market_cap = data.get('ath_market_cap', 0)
            
            # Логируем маркеткапы
            logger.info(f"Токен {query} - Initial mcap: {initial_mcap}, ATH mcap: {ath_market_cap}")
            
            # Пропускаем токены без данных о маркет капе
            if not initial_mcap or not ath_market_cap:
                logger.info(f"Токен {query} не имеет данных о маркеткапе, пропускаем")
                continue
            
            # Вычисляем множитель на основе ATH
            multiplier = ath_market_cap / initial_mcap if initial_mcap > 0 else 0
            logger.info(f"Токен {query} - Множитель: {multiplier:.2f}x")
            
            # Обновляем счетчики - используем взаимоисключающие категории
            total_tokens += 1
            
            if multiplier >= 5:
                tokens_5x += 1
            elif multiplier >= 2:
                tokens_2x += 1
            elif multiplier >= 1.5:
                tokens_1_5x += 1
            
            # Добавляем в список для подробного логирования
            ticker = "Неизвестно"
            if 'token_info' in data and 'ticker' in data['token_info']:
                ticker = data['token_info']['ticker']
                
            analyzed_tokens.append({
                'query': query,
                'ticker': ticker,
                'added_time': token_added_time,
                'initial_mcap': initial_mcap,
                'ath_mcap': ath_market_cap,
                'multiplier': multiplier
            })
        
        # Логируем подробную статистику по токенам
        logger.info(f"Проанализировано токенов за последние 12 часов: {total_tokens}")
        logger.info(f"Токенов с ростом от 1.5x до <2x: {tokens_1_5x}")
        logger.info(f"Токенов с ростом от 2x до <5x: {tokens_2x}")
        logger.info(f"Токенов с ростом ≥5x: {tokens_5x}")
        
        for token in analyzed_tokens:
            logger.info(f"Токен {token['ticker']} ({token['query']}): добавлен {token['added_time']}, множитель {token['multiplier']:.2f}x")
        
        # Формируем сообщение со статистикой
        if total_tokens > 0:
            # Вычисляем процент успешных токенов (>=1.5x)
            successful_tokens = tokens_1_5x + tokens_2x + tokens_5x
            hitrate_percent = (successful_tokens / total_tokens) * 100 if total_tokens > 0 else 0
            
            # Определяем символ для визуализации процента успеха
            hitrate_symbol = "🔴"  # <30%
            if hitrate_percent >= 70:
                hitrate_symbol = "🟣"  # >=70%
            elif hitrate_percent >= 50:
                hitrate_symbol = "🟢"  # >=50%
            elif hitrate_percent >= 30:
                hitrate_symbol = "🟡"  # >=30%
            
            message = (
                f"Token stats for the last 12 hours:\n"
                f"> Total tokens: {total_tokens}\n"
                f"├ 1.5x-2x: {tokens_1_5x}\n"
                f"├ 2x-5x: {tokens_2x}\n"
                f"└ ≥5x: {tokens_5x}\n\n"
                f"Hitrate: {hitrate_percent:.1f}% {hitrate_symbol} (1.5x+)"
            )
            
            # Получаем список chat_id для отправки сообщения
            # Берем уникальные chat_id из всех токенов в хранилище
            chat_ids = set()
            for query, data in all_tokens.items():
                chat_id = data.get('chat_id')
                if chat_id:
                    chat_ids.add(chat_id)
            
            logger.info(f"Найдено {len(chat_ids)} уникальных chat_id для отправки статистики: {chat_ids}")
            
            # Если нет chat_id, используем значение из активного бота или токена
            if not chat_ids:
                logger.warning("Не найдено ни одного chat_id для отправки статистики")
                logger.info("Попробуем найти chat_id из активных токенов...")
                
                for query, data in all_tokens.items():
                    if not data.get('hidden', False):
                        message_id = data.get('message_id', 0)
                        chat_id = data.get('chat_id', 0)
                        
                        if chat_id:
                            chat_ids.add(chat_id)
                            logger.info(f"Найден chat_id {chat_id} для активного токена {query}")
            
            # Если по-прежнему нет chat_id, отправим сообщение об ошибке
            if not chat_ids:
                logger.error("Не удалось найти ни одного chat_id для отправки сообщения")
                return
            
            # Отправляем сообщение в каждый чат
            success_count = 0
            for chat_id in chat_ids:
                try:
                    logger.info(f"Отправка статистики в чат {chat_id}...")
                    
                    # Добавляем обработку повторных попыток для отправки
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=message
                            )
                            logger.info(f"Статистика токенов успешно отправлена в чат {chat_id}")
                            success_count += 1
                            break
                        except (TimedOut, NetworkError) as e:
                            if attempt < max_retries - 1:
                                logger.warning(f"Таймаут при отправке статистики в чат {chat_id} (попытка {attempt+1}/{max_retries}): {e}")
                                await asyncio.sleep(2)  # пауза перед повторной попыткой
                            else:
                                logger.error(f"Не удалось отправить статистику в чат {chat_id} после {max_retries} попыток: {e}")
                except Exception as e:
                    logger.error(f"Ошибка при отправке статистики в чат {chat_id}: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
            
            logger.info(f"Статистика успешно отправлена в {success_count} из {len(chat_ids)} чатов")
        else:
            logger.info("Нет токенов за последние 12 часов для формирования статистики")
        
        logger.info("=== ЗАВЕРШЕНИЕ ФОРМИРОВАНИЯ СТАТИСТИКИ ПО ТОКЕНАМ ===")
    except Exception as e:
        logger.error(f"Ошибка при формировании статистики по токенам: {e}")
        import traceback
        logger.error(traceback.format_exc())

async def check_market_cap_only(
    query: str,
    chat_id: int,
    context: Optional[ContextTypes.DEFAULT_TYPE] = None
) -> Optional[Dict[str, Any]]:
    """Проверяет только Market Cap токена без обновления остальных данных."""
    try:
        # Получаем данные о токене из хранилища
        stored_data = token_storage.get_token_data(query)
        if not stored_data:
            logger.warning(f"Не найдены данные о токене {query} для обновления Market Cap")
            return None
        
        logger.info(f"Запрос обновления Market Cap для токена {query}")
        
        # Добавляем повторные попытки в случае таймаута
        max_retries = 3
        response = None
        
        for attempt in range(max_retries):
            try:
                response = requests.get(f"{DEXSCREENER_API_URL}?q={query}", timeout=10)
                break
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Таймаут при запросе к API ({attempt+1}/{max_retries}): {e}")
                    await asyncio.sleep(2)  # пауза перед повторной попыткой
                else:
                    logger.error(f"Не удалось подключиться к API после {max_retries} попыток: {e}")
                    return None
        
        if not response:
            return None
        
        if response.status_code == 200:
            data = response.json()
            pairs = data.get('pairs', [])
            
            if not pairs:
                logger.warning(f"API не вернуло данные о парах для токена {query}")
                return None
            
            # Берем первый результат
            token_data = pairs[0]
            
            # Получаем и обновляем market cap
            market_cap = token_data.get('fdv')
            raw_market_cap = market_cap  # Сохраняем исходное значение
            market_cap_formatted = format_number(market_cap)
            
            # Обновляем только поле market_cap в хранилище
            if 'token_info' in stored_data:
                stored_data['token_info']['market_cap'] = market_cap_formatted
                stored_data['token_info']['raw_market_cap'] = raw_market_cap
                
                # Обновляем данные в хранилище
                token_storage.store_token_data(query, stored_data)
                
                # Обновляем ATH, если текущее значение выше
                if raw_market_cap:
                    token_storage.update_token_ath(query, raw_market_cap)
                
                logger.info(f"Обновлен Market Cap для токена {query}: {market_cap_formatted}")
                
                return {'market_cap': market_cap_formatted, 'raw_market_cap': raw_market_cap}
            else:
                logger.warning(f"В хранилище нет поля token_info для токена {query}")
                return None
        else:
            logger.warning(f"API вернуло ошибку {response.status_code} для токена {query}")
            return None
            
    except Exception as e:
        logger.error(f"Ошибка при проверке Market Cap для токена {query}: {e}")
        return None

async def generate_excel(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    """Генерирует Excel файл со всеми данными о токенах."""
    try:
        # Получаем все активные токены
        active_tokens = token_storage.get_active_tokens()
        
        if not active_tokens:
            await context.bot.send_message(
                chat_id=chat_id,
                text="Нет активных токенов для генерации Excel файла."
            )
            return
        
        # Подготавливаем данные для Excel
        tokens_data = []
        
        for query, token_data in active_tokens.items():
            try:
                token_info = token_data.get('token_info', {})
                initial_data = token_data.get('initial_data', {})
                ath_market_cap = token_data.get('ath_market_cap', 0)
                
                # Получаем базовую информацию о токене
                ticker = token_info.get('ticker', 'Неизвестно')
                ticker_address = token_info.get('ticker_address', 'Неизвестно')
                
                # Получаем данные о маркет капах
                current_market_cap = token_info.get('raw_market_cap', 0)
                initial_market_cap = initial_data.get('raw_market_cap', 0)
                
                # Вычисляем множитель роста более точно - используем ATH / initial
                multiplier = 1.0
                if initial_market_cap and ath_market_cap and isinstance(initial_market_cap, (int, float)) and isinstance(ath_market_cap, (int, float)) and initial_market_cap > 0:
                    multiplier = round(ath_market_cap / initial_market_cap, 2)
                
                # Данные о возрасте токена
                token_age = token_info.get('token_age', 'Неизвестно')
                
                # Информация о времени добавления
                added_time = datetime.datetime.fromtimestamp(token_data.get('added_time', 0)).strftime('%Y-%m-%d %H:%M:%S')
                
                # Получаем время достижения ATH
                ath_time = "Неизвестно"
                if 'ath_time' in token_data:
                    ath_timestamp = token_data.get('ath_time', 0)
                    if ath_timestamp:
                        ath_time = datetime.datetime.fromtimestamp(ath_timestamp).strftime('%Y-%m-%d %H:%M:%S')
                
                # Получаем информацию о DEX
                dex_info = "Неизвестно"
                if 'dex_info' in token_info:
                    dex_info = token_info.get('dex_info', 'Неизвестно')
                
                # Получаем полные данные о тренде транзакций и формируем строку
                txns_data_str = "Нет данных"
                if 'txns_trend' in token_info:
                    txns_trend = token_info.get('txns_trend', {})
                    txns_str_parts = []
                    
                    # m5
                    m5_buys = txns_trend.get('m5_buys', 0)
                    m5_sells = txns_trend.get('m5_sells', 0)
                    if m5_buys > 0 or m5_sells > 0:
                        txns_str_parts.append(f"m5: {m5_buys}/{m5_sells}")
                    
                    # h1
                    h1_buys = txns_trend.get('h1_buys', 0)
                    h1_sells = txns_trend.get('h1_sells', 0)
                    if h1_buys > 0 or h1_sells > 0:
                        txns_str_parts.append(f"h1: {h1_buys}/{h1_sells}")
                    
                    # h24
                    h24_buys = txns_trend.get('h24_buys', 0)
                    h24_sells = txns_trend.get('h24_sells', 0)
                    if h24_buys > 0 or h24_sells > 0:
                        txns_str_parts.append(f"h24: {h24_buys}/{h24_sells}")
                    
                    if txns_str_parts:
                        txns_data_str = ", ".join(txns_str_parts)
                
                # Получаем полную информацию о PumpFun
                pumpfun_data_str = "Нет"
                has_boosts = "Нет"
                if 'pumpfun_data' in token_info:
                    pumpfun_data = token_info.get('pumpfun_data', {})
                    if pumpfun_data:
                        # Извлекаем txns
                        pumpfun_txns = pumpfun_data.get('txns', {})
                        txns_str_parts = []
                        
                        # m5
                        m5 = pumpfun_txns.get('m5', {})
                        if m5:
                            txns_str_parts.append(f"m5: {m5.get('buys', 0)}/{m5.get('sells', 0)}")
                        
                        # h1
                        h1 = pumpfun_txns.get('h1', {})
                        if h1:
                            txns_str_parts.append(f"h1: {h1.get('buys', 0)}/{h1.get('sells', 0)}")
                        
                        # h6
                        h6 = pumpfun_txns.get('h6', {})
                        if h6:
                            txns_str_parts.append(f"h6: {h6.get('buys', 0)}/{h6.get('sells', 0)}")
                        
                        # h24
                        h24 = pumpfun_txns.get('h24', {})
                        if h24:
                            txns_str_parts.append(f"h24: {h24.get('buys', 0)}/{h24.get('sells', 0)}")
                        
                        pumpfun_data_str = ", ".join(txns_str_parts)
                        
                        # Проверяем наличие бустов
                        boosts = pumpfun_data.get('boosts')
                        if boosts:
                            has_boosts = "Да"
                
                # Форматируем маркет капы для отображения
                current_market_cap_formatted = format_number(current_market_cap) if isinstance(current_market_cap, (int, float)) else "Неизвестно"
                initial_market_cap_formatted = format_number(initial_market_cap) if isinstance(initial_market_cap, (int, float)) else "Неизвестно"
                ath_market_cap_formatted = format_number(ath_market_cap) if isinstance(ath_market_cap, (int, float)) else "Неизвестно"
                            
                # Получаем информацию о количестве сигналов из каналов
                channel_count = 0
                channels = []
                first_seen = "Неизвестно"
                signal_reached_time = "Неизвестно"
                
                # Загружаем данные из файла отслеживания токенов, если он существует
                try:
                    TRACKER_DB_FILE = 'tokens_tracker_database.json'
                    if os.path.exists(TRACKER_DB_FILE):
                        with open(TRACKER_DB_FILE, 'r', encoding='utf-8') as f:
                            tracker_data = json.load(f)
                            
                        # Проверяем есть ли данные о токене в базе отслеживания
                        if query in tracker_data:
                            token_tracker_data = tracker_data[query]
                            channel_count = token_tracker_data.get('channel_count', 0)
                            channels = token_tracker_data.get('channels', [])
                            first_seen = token_tracker_data.get('first_seen', 'Неизвестно')
                            signal_reached_time = token_tracker_data.get('signal_reached_time', 'Неизвестно')
                        else:
                            # Если не нашли по точному совпадению, пробуем поискать адрес в ключах
                            for tracker_query, tracker_data_item in tracker_data.items():
                                if query in tracker_query or tracker_query in query:
                                    channel_count = tracker_data_item.get('channel_count', 0)
                                    channels = tracker_data_item.get('channels', [])
                                    first_seen = tracker_data_item.get('first_seen', 'Неизвестно')
                                    signal_reached_time = tracker_data_item.get('signal_reached_time', 'Неизвестно')
                                    break
                except Exception as e:
                    logger.error(f"Ошибка при загрузке данных из файла отслеживания: {e}")
                
                # Формируем данные для Excel (только начальные данные)
                # Расставляем столбцы логически, группируя связанные данные
                row = {
                    # Базовая информация о токене
                    'Тикер': ticker,
                    'Адрес токена': ticker_address,
                    'Возраст токена': token_age,
                    'Дата добавления': added_time,
                    
                    # Данные о сигналах из каналов (из tokens_tracker_database)
                    'Количество сигналов': channel_count,
                    'Первое обнаружение': first_seen,
                    'Время достижения сигнала': signal_reached_time,
                    
                    # Данные о Market Cap
                    'Market Cap (начальный)': initial_market_cap_formatted,
                    'Market Cap (ATH)': ath_market_cap_formatted,
                    'Время достижения ATH': ath_time,
                    'Множитель роста': f"{multiplier}x",
                    
                    # Данные о DEX и транзакциях
                    'DEX': dex_info,
                    'Транзакции': txns_data_str,
                    'PumpFun транзакции': pumpfun_data_str,
                    'PumpFun бусты': has_boosts,
                }
                
                # Добавляем список каналов, если они есть
                if channels:
                    row['Каналы'] = ', '.join(channels)
                
                # Добавляем данные о объемах торгов
                if 'volume_5m' in token_info:
                    row['Объем за 5 минут'] = token_info.get('volume_5m', 'Неизвестно')
                
                if 'volume_1h' in token_info:
                    row['Объем за 1 час'] = token_info.get('volume_1h', 'Неизвестно')
                
                # Добавляем информацию о социальных сетях и сайтах если есть
                websites = token_info.get('websites', [])
                socials = token_info.get('socials', [])
                
                if websites:
                    website_links = [f"{website.get('label', 'Website')}: {website.get('url', '')}" 
                                    for website in websites if website.get('url')]
                    row['Сайты'] = '; '.join(website_links)
                
                if socials:
                    social_links = [f"{social.get('type', '').capitalize()}: {social.get('url', '')}" 
                                    for social in socials if social.get('url') and social.get('type')]
                    row['Соцсети'] = '; '.join(social_links)
                
                # Добавляем только одну строку (начальную) в данные
                tokens_data.append(row)
                
            except Exception as e:
                logger.error(f"Ошибка при обработке токена {query} для Excel: {e}")
                import traceback
                logger.error(traceback.format_exc())
        
        # Создаем DataFrame и сохраняем Excel файл
        df = pd.DataFrame(tokens_data)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f'tokens_data_{timestamp}.xlsx'
        
        # Настраиваем параметры Excel файла
        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Tokens Data')
            
            # Получаем объект листа для форматирования
            worksheet = writer.sheets['Tokens Data']
            
            # Настраиваем ширину столбцов
            for idx, col in enumerate(df.columns):
                max_len = max(
                    df[col].astype(str).map(len).max(),  # длина самого длинного значения
                    len(str(col))  # длина заголовка
                )
                # Устанавливаем ширину столбца (с небольшим запасом)
                worksheet.column_dimensions[chr(65 + idx)].width = max_len + 2
        
        # Отправляем файл пользователю
        try:
            with open(filename, 'rb') as excel_file:
                await context.bot.send_document(
                    chat_id=chat_id, 
                    document=excel_file, 
                    caption="📊 Excel файл с данными о токенах."
                )
            
            # Удаляем временный файл
            os.remove(filename)
        except Exception as e:
            logger.error(f"Ошибка при отправке Excel файла: {e}")
            await context.bot.send_message(
                chat_id=chat_id,
                text="Не удалось отправить Excel файл. Пожалуйста, попробуйте позже."
            )
        
    except Exception as e:
        logger.error(f"Ошибка при генерации Excel файла: {e}")
        await context.bot.send_message(
        chat_id=chat_id,
            text="Произошла ошибка при генерации Excel файла. Пожалуйста, попробуйте позже."
        )