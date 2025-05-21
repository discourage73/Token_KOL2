import os
import logging
import time
import asyncio
import datetime
import traceback
import requests
import telegram
from typing import Dict, Any, Optional, List, Tuple

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
from telegram.error import TimedOut, NetworkError

# Импортируем модули проекта
import token_storage
from config import TELEGRAM_TOKEN, logger
from utils import format_number, format_tokens_list

# Импортируем функции из token_service, модифицируем для тестового бота
from token_service import (
    get_token_info as original_get_token_info,
    process_token_address, 
    check_all_market_caps, 
    check_market_cap_only
)

# Обновляем импорты из test_bot_commands
from test_bot_commands import (
    start,
    help_command,
    list_tokens,
    excel_command,
    clear_tokens,
    handle_clear_confirm,
    handle_clear_cancel,
    handle_refresh_list,
    handle_generate_excel,
    setup_bot_commands,
    setup_commands_direct,
    # Добавляем новые функции
    handle_clear_all_confirm,
    handle_clear_selective,
    handle_hide_token,
    handle_manage_hidden,
    handle_unhide_token,
    handle_clear_return,
    # Новые функции для полного удаления токенов
    handle_delete_all_confirm,
    handle_delete_confirm,
    handle_delete_selective,
    handle_delete_token
)

# Создаем директорию для логов, если она не существует
if not os.path.exists('logs'):
    os.makedirs('logs')

# Настройка логирования для отладки
debug_logger = logging.getLogger('debug')
debug_logger.setLevel(logging.DEBUG)
# Создаем обработчик файла для логирования ошибок
debug_handler = logging.FileHandler('logs/debug.log', encoding='utf-8')
debug_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
debug_logger.addHandler(debug_handler)

# Добавляем вывод логов в консоль
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('%(levelname)s: %(message)s')
console_handler.setFormatter(console_formatter)
debug_logger.addHandler(console_handler)

# Функция для получения данных о DEX
def fetch_dex_data(contract_address: str) -> Dict[str, Any]:
    """
    Получает данные о DEX напрямую из API DexScreener.
    """
    try:
        debug_logger.info(f"Запрос данных о DEX для контракта: {contract_address}")
        url = f"https://api.dexscreener.com/latest/dex/tokens/{contract_address}"
        
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            debug_logger.info(f"Успешно получены данные о DEX для контракта: {contract_address}")
            
            # Логируем количество пар и их названия для отладки
            pairs = data.get('pairs', [])
            dex_names = [pair.get('dexId', 'Unknown') for pair in pairs]
            debug_logger.info(f"Получены данные о {len(pairs)} парах. DEX: {', '.join(dex_names)}")
            
            return data
        else:
            debug_logger.warning(f"Ошибка {response.status_code} при запросе данных о DEX")
            return {"pairs": []}
    except Exception as e:
        debug_logger.error(f"Исключение при запросе данных о DEX: {str(e)}")
        debug_logger.error(traceback.format_exc())
        return {"pairs": []}

async def get_token_info(
    query: str, 
    chat_id: int, 
    message_id: Optional[int] = None, 
    context: Optional[ContextTypes.DEFAULT_TYPE] = None
) -> Optional[Dict[str, Any]]:
    """Получает информацию о токене и отправляет или обновляет сообщение с расширенной информацией."""
    try:
        # Вызываем оригинальную функцию только для получения данных, без отправки сообщения
        if message_id is None:
            token_info = await original_get_token_info(query, None, None, None)
        else:
            # Если обновляем существующее сообщение, используем нашу версию форматирования
            # и не позволяем original_get_token_info обновлять сообщение
            token_info = await original_get_token_info(query, None, None, None)
            
        if not token_info:
            return None
        
        # Получаем дополнительные данные из хранилища
        stored_data = token_storage.get_token_data(query)
        
        # Если данных нет, создаем начальные данные перед любыми операциями
        if not stored_data:
            # Сохраняем начальные данные для нового токена
            current_time = datetime.datetime.now().strftime("%H:%M:%S")
            initial_data = {
                'time': current_time,
                'market_cap': token_info.get('market_cap', 'Неизвестно'),
                'raw_market_cap': token_info.get('raw_market_cap', 0)
            }
            stored_data = {
                'initial_data': initial_data,
                'token_info': token_info
            }
        
        # По умолчанию устанавливаем значения
        token_info['dex_info'] = 'Unknown DEX'
        token_info['txns_trend'] = {
            "m5_buys": 0,
            "m5_sells": 0,
            "h1_buys": 0,
            "h1_sells": 0,
            "h24_buys": 0,
            "h24_sells": 0,
            "status": "🟡 Нейтральный тренд"
        }
        
        # Запрашиваем данные напрямую с API для получения данных о всех DEX
        try:
            # Важное изменение: используем правильную конструкцию адреса токена при запросе
            dex_data = fetch_dex_data(query)
            
            if dex_data and 'pairs' in dex_data and dex_data['pairs']:
                pairs = dex_data.get('pairs', [])
                
                # Используем нашу функцию для нахождения популярного DEX и PUMPFUN DEX
                popular_dex, pumpfun_dex = find_dexes_info(dex_data)
                
                # Обрабатываем основной DEX
                if popular_dex:
                    token_info['dex_info'] = popular_dex.get('dexId', 'Unknown DEX')
                    #token_info['txns_trend'] = analyze_transactions(popular_dex.get('txns', {}))
                
                # Добавляем информацию о PUMPFUN, если найден
                if pumpfun_dex:
                    token_info['pumpfun_data'] = {
                        'txns': pumpfun_dex.get('txns', {}),
                        'boosts': pumpfun_dex.get('boosts', {}).get('active', None)
                    }
        except Exception as e:
            debug_logger.error(f"Ошибка при получении данных DEX: {str(e)}")
            debug_logger.error(traceback.format_exc())
        
        # Форматируем сообщение с расширенной информацией
        message = format_enhanced_message(token_info, stored_data.get('initial_data', {}))
        
        # Создаем кнопку обновления
        keyboard = [[InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh:{query}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Если есть context и chat_id, отправляем или обновляем сообщение
        if context and chat_id:
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
                        'initial_data': stored_data.get('initial_data', {}),
                        'token_info': token_info,
                        'last_alert_multiplier': stored_data.get('last_alert_multiplier', 1),
                        'added_time': stored_data.get('added_time', time.time()),
                        'raw_api_data': stored_data.get('raw_api_data', {})
                    }
                    
                    token_storage.store_token_data(query, token_data_to_store)
                except Exception as e:
                    logger.error(f"Ошибка при отправке нового сообщения: {e}")
        
        return token_info
    except Exception as e:
        logger.error(f"Ошибка в get_token_info: {str(e)}")
        return None
        
        
def find_dexes_info(dex_data: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Находит основной DEX и PUMPFUN DEX из данных, полученных от API.
    Возвращает кортеж (основной_dex, pumpfun_dex)
    """
    try:
        pairs = dex_data.get("pairs", [])
        debug_logger.info(f"Анализ {len(pairs)} пар DEX")
        
        popular_dex = None
        pumpfun_dex = None
        max_txns = 0
        
        # Если найдено менее 2-х пар, сразу логируем это для отладки
        if len(pairs) < 2:
            debug_logger.info(f"Внимание: получено только {len(pairs)} пар DEX")
        
        for pair in pairs:
            dex_id = pair.get('dexId', 'Unknown')
            txns = pair.get('txns', {})
            
            # Логируем каждую пару для отладки
            debug_logger.info(f"Обрабатываем DEX: {dex_id}, URL: {pair.get('url', 'No URL')}")
            
            # Считаем общее количество транзакций за 24 часа
            h24_data = txns.get('h24', {})
            h24_buys = h24_data.get('buys', 0) if isinstance(h24_data, dict) else 0
            h24_sells = h24_data.get('sells', 0) if isinstance(h24_data, dict) else 0
            total_txns = h24_buys + h24_sells
            
            debug_logger.info(f"DEX: {dex_id}, Транзакции (24ч): {total_txns} (покупки: {h24_buys}, продажи: {h24_sells})")
            
            # Проверяем, не PUMPFUN ли это (проверяем все варианты написания)
            if dex_id.lower() in ['pumpfun', 'pump.fun', 'pump fun']:
                pumpfun_dex = pair
                debug_logger.info(f"Найден PUMPFUN DEX")
            
            # Проверяем, не самый ли это популярный DEX
            if total_txns > max_txns:
                max_txns = total_txns
                popular_dex = pair
                debug_logger.info(f"Найден новый популярный DEX: {dex_id} с {total_txns} транзакциями")
        
        # Если популярный DEX не найден, берем первую пару, если она есть
        if not popular_dex and pairs:
            popular_dex = pairs[0]
            debug_logger.info(f"Используем первую пару как основную: {popular_dex.get('dexId', 'Unknown')}")
        
        # Если popular_dex существует, логируем его для отладки
        if popular_dex:
            debug_logger.info(f"Итоговый выбор популярного DEX: {popular_dex.get('dexId', 'Unknown')}")
        else:
            debug_logger.warning("Популярный DEX не найден")
        
        return popular_dex, pumpfun_dex
    except Exception as e:
        debug_logger.error(f"Ошибка при анализе DEX: {str(e)}")
        debug_logger.error(traceback.format_exc())
        return None, None

# Удаляем функцию analyze_transactions полностью

async def get_token_info(
    query: str, 
    chat_id: int, 
    message_id: Optional[int] = None, 
    context: Optional[ContextTypes.DEFAULT_TYPE] = None
) -> Optional[Dict[str, Any]]:
    """Получает информацию о токене и отправляет или обновляет сообщение с расширенной информацией."""
    try:
        # Вызываем оригинальную функцию только для получения данных, без отправки сообщения
        if message_id is None:
            token_info = await original_get_token_info(query, None, None, None)
        else:
            # Если обновляем существующее сообщение, используем нашу версию форматирования
            # и не позволяем original_get_token_info обновлять сообщение
            token_info = await original_get_token_info(query, None, None, None)
            
        if not token_info:
            return None
        
        # Получаем дополнительные данные из хранилища
        stored_data = token_storage.get_token_data(query)
        
        # Если данных нет, создаем начальные данные перед любыми операциями
        if not stored_data:
            # Сохраняем начальные данные для нового токена
            current_time = datetime.datetime.now().strftime("%H:%M:%S")
            initial_data = {
                'time': current_time,
                'market_cap': token_info.get('market_cap', 'Неизвестно'),
                'raw_market_cap': token_info.get('raw_market_cap', 0)
            }
            stored_data = {
                'initial_data': initial_data,
                'token_info': token_info
            }
        
        # По умолчанию устанавливаем значения
        token_info['dex_info'] = 'Unknown DEX'
        # Убираем txns_trend, так как анализ транзакций удален
        
        # Запрашиваем данные напрямую с API для получения данных о всех DEX
        try:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{query}"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                dex_data = response.json()
                pairs = dex_data.get('pairs', [])
                
                popular_dex = None
                pumpfun_dex = None
                max_txns = 0
                
                # Находим PUMPFUN и самый популярный DEX
                for pair in pairs:
                    dex_id = pair.get('dexId', 'Unknown')
                    txns = pair.get('txns', {})
                    
                    # Считаем общее количество транзакций за 24 часа
                    h24_data = txns.get('h24', {})
                    h24_buys = h24_data.get('buys', 0) if isinstance(h24_data, dict) else 0
                    h24_sells = h24_data.get('sells', 0) if isinstance(h24_data, dict) else 0
                    total_txns = h24_buys + h24_sells
                    
                    # Проверяем, не PUMPFUN ли это
                    if dex_id.lower() in ['pumpfun', 'pump.fun', 'pump fun']:
                        pumpfun_dex = pair
                    
                    # Проверяем, не самый ли это популярный DEX
                    if total_txns > max_txns:
                        max_txns = total_txns
                        popular_dex = pair
                
                # Если популярный DEX не найден, берем первую пару, если она есть
                if not popular_dex and pairs:
                    popular_dex = pairs[0]
                
                # Обрабатываем основной DEX
                if popular_dex:
                    token_info['dex_info'] = popular_dex.get('dexId', 'Unknown DEX')
                    # Убираем вызов analyze_transactions здесь
                
                # Добавляем информацию о PUMPFUN, если найден
                if pumpfun_dex:
                    token_info['pumpfun_data'] = {
                        'txns': pumpfun_dex.get('txns', {}),
                        'boosts': pumpfun_dex.get('boosts', {}).get('active', None)
                    }
        except Exception:
            pass  # Продолжаем работу даже при ошибке API
        
        # Форматируем сообщение с расширенной информацией
        message = format_enhanced_message(token_info, stored_data.get('initial_data', {}))
        
        # Создаем кнопку обновления
        keyboard = [[InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh:{query}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Если есть context и chat_id, отправляем или обновляем сообщение
        if context and chat_id:
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
                        'initial_data': stored_data.get('initial_data', {}),
                        'token_info': token_info,
                        'last_alert_multiplier': stored_data.get('last_alert_multiplier', 1),
                        'added_time': stored_data.get('added_time', time.time()),
                        'raw_api_data': stored_data.get('raw_api_data', {})
                    }
                    
                    token_storage.store_token_data(query, token_data_to_store)
                except Exception as e:
                    logger.error(f"Ошибка при отправке нового сообщения: {e}")
        
        return token_info
    except Exception as e:
        logger.error(f"Ошибка в get_token_info: {str(e)}")
        return None

def format_enhanced_message(token_info: Dict[str, Any], initial_data: Optional[Dict[str, Any]] = None) -> str:
    """Форматирует расширенное сообщение с дополнительной информацией о токене."""
    try:
        debug_logger.info(f"Форматирование сообщения для токена: {token_info.get('ticker', 'Неизвестно')}")
        
        # Создаем ссылку на поиск адреса в Twitter/X.com
        ticker_address = token_info.get('ticker_address', '')
        twitter_search_link = f"https://twitter.com/search?q={ticker_address}"
        
        message = f"🪙 *Тикер*: {token_info.get('ticker', 'Неизвестно')} [Xca]({twitter_search_link})\n"
        message += f"📝 *Адрес*: `{token_info.get('ticker_address', 'Неизвестно')}`\n\n"
        
        # Блок с ссылками на сайты (перемещен вверх)
        if 'websites' in token_info and token_info.get('websites'):
            website_links = [f"[{website.get('label', 'Website')}]({website.get('url', '')})" 
                           for website in token_info.get('websites', []) if website.get('url')]
            
            if website_links:
                message += f"🌐 *Сайты*: {' | '.join(website_links)}\n"
                debug_logger.info(f"Добавлены ссылки на сайты: {website_links}")
        
        # Блок с ссылками на соцсети (перемещен вверх)
        if 'socials' in token_info and token_info.get('socials'):
            social_links = [f"[{social.get('type', '').capitalize()}]({social.get('url', '')})" 
                          for social in token_info.get('socials', []) if social.get('url') and social.get('type')]
            
            if social_links:
                message += f"📱 *Соцсети*: {' | '.join(social_links)}\n\n"
                debug_logger.info(f"Добавлены ссылки на соцсети: {social_links}")
        else:
            message += "\n"  # Добавляем дополнительный перенос, если нет соцсетей
        
        message += f"💰 *Market Cap*: {token_info.get('market_cap', 'Неизвестно')}\n"
        
        # Проверяем изменение маркет капа, если есть начальные данные
        if (initial_data and 'raw_market_cap' in initial_data and 
            initial_data['raw_market_cap'] and 'raw_market_cap' in token_info and token_info['raw_market_cap']):
            initial_mcap = initial_data['raw_market_cap']
            current_mcap = token_info['raw_market_cap']
            
            # Вычисляем множитель
            if initial_mcap > 0:
                multiplier = current_mcap / initial_mcap
                
                # Если множитель больше 2, добавляем информацию
                if multiplier >= 2:
                    # Округляем множитель до целого числа, если он больше 10, иначе до одного знака после запятой
                    mult_formatted = int(multiplier) if multiplier >= 10 else round(multiplier, 1)
                    message += f"🔥 *Рост: x{mult_formatted}* от начального значения!\n"
                    debug_logger.info(f"Добавлена информация о росте: x{mult_formatted}")
        
        message += f"⏱️ *Возраст токена*: {token_info.get('token_age', 'Неизвестно')}\n\n"
        
        # Блок с объемами торгов
        volumes_block = ""
        if token_info.get('volume_5m', 'Неизвестно') != "Неизвестно":
            volumes_block += f"📈 *Объем (5м)*: {token_info['volume_5m']}\n"
            
        if token_info.get('volume_1h', 'Неизвестно') != "Неизвестно":
            volumes_block += f"📈 *Объем (1ч)*: {token_info['volume_1h']}\n"
        
        if volumes_block:
            message += volumes_block + "\n"
        
        # Получаем адрес токена для ссылок
        ticker_address = token_info.get('ticker_address', '')
        pair_address = token_info.get('pair_address', '')
        
        # Создаем ссылку на GMGN
        gmgn_link = f"https://gmgn.ai/sol/token/{ticker_address}"
        
        # Блок с ссылками на торговые площадки
        message += f"🔎 *Ссылки*: [DexScreener]({token_info.get('dexscreener_link', '#')}) | [Axiom Trade]({token_info.get('axiom_link', '#')}) | [GMGN]({gmgn_link})\n\n"
        
        # УДАЛЯЕМ БЛОК С ИНФОРМАЦИЕЙ О DEX - эти строки нужно удалить или закомментировать
        # # Добавляем информацию о DEX без анализа транзакций
        # if 'dex_info' in token_info:
        #     dex_name = token_info['dex_info'].upper()
        #     message += f"DEX: {dex_name}\n\n"
        #     debug_logger.info(f"Добавлена информация о DEX: {dex_name}")
        # 
        # # Добавляем информацию о PUMPFUN, если она доступна (только без анализа)
        # if 'pumpfun_data' in token_info:
        #     message += f"DEX: *PUMPFUN*\n\n"
        #     
        #     # Добавляем информацию о бустах, если есть
        #     boosts = token_info['pumpfun_data'].get('boosts')
        #     if boosts:
        #         message += f"Активация бустов: {boosts}\n\n"
        #     debug_logger.info("Добавлена информация о PUMPFUN")
        
        # Добавляем метку времени и исходные данные
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        message += f"_Обновлено: {current_time}_"
        
        # Добавляем информацию о первоначальном запросе, если она доступна
        if initial_data:
            if 'time' in initial_data:
                message += f"\n_Первый запрос: {initial_data['time']}_"
            if 'market_cap' in initial_data:
                message += f"\n_Начальный Market Cap: {initial_data['market_cap']}_"
        
        debug_logger.info("Форматирование сообщения завершено успешно")
        return message
    except Exception as e:
        debug_logger.error(f"Ошибка при форматировании сообщения: {str(e)}")
        debug_logger.error(traceback.format_exc())
        # В случае ошибки возвращаем базовое сообщение
        return f"🪙 *Тикер*: {token_info.get('ticker', 'Неизвестно')}\n📝 *Адрес*: `{token_info.get('ticker_address', 'Неизвестно')}`\n\n💰 *Market Cap*: {token_info.get('market_cap', 'Неизвестно')}\n\n_Ошибка при форматировании полного сообщения_"

async def extract_token_address_from_message(text: str) -> str:
    """Извлекает адрес контракта токена из сообщения."""
    try:
        import re
        
        # Ищем строку, начинающуюся с "Контракт: " или "Contract: "
        contract_pattern = r'(?:Контракт|Contract):\s*([a-zA-Z0-9]{32,44})'
        matches = re.search(contract_pattern, text)
        
        if matches:
            # Если нашли такой шаблон, возвращаем только группу с адресом
            return matches.group(1)
        
        # Если не нашли по шаблону Контракт:, ищем просто адрес Solana
        # Solana адрес токена (32-44 символа)
        solana_pattern = r'\b[a-zA-Z0-9]{32,44}\b'
        matches = re.search(solana_pattern, text)
        
        if matches:
            return matches.group(0)
            
        # Ищем Ethereum/BSC адрес
        eth_pattern = r'0x[0-9a-fA-F]{40}'
        matches = re.search(eth_pattern, text)
        
        if matches:
            return matches.group(0)
        
        # Если ничего не нашли
        return ""
    except Exception as e:
        logger.error(f"Ошибка в extract_token_address_from_message: {str(e)}")
        logger.error(traceback.format_exc())
        return ""

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает входящие сообщения."""
    if not update.message:
        return
    
    # Проверяем, есть ли текст в сообщении
    if update.message.text:
        query = update.message.text.strip()
        
        # Отслеживаем проблемный запрос
        debug_logger.info(f"Получен запрос: {query}")
        
        try:
            # Извлекаем адрес токена из сообщения, если это пересланное сообщение
            token_address = await extract_token_address_from_message(query)
            
            # Если нашли адрес, используем его вместо исходного запроса
            if token_address:
                query = token_address
                debug_logger.info(f"Найден адрес токена в сообщении. Используем его: {query}")
        
            # Отправляем сообщение о поиске
            debug_logger.info(f"Получено сообщение: {query}")
            try:
                # Используем конструкцию try-except для отправки сообщения
                # с несколькими попытками и обработкой таймаутов
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        msg = await update.message.reply_text(f"Ищу информацию о токене: {query}...")
                        debug_logger.info(f"Отправлено сообщение о поиске")
                        break  # выходим из цикла если успешно
                    except (TimedOut, NetworkError) as e:
                        if attempt < max_retries - 1:
                            debug_logger.warning(f"Таймаут при отправке ({attempt+1}/{max_retries}): {e}")
                            await asyncio.sleep(2)  # пауза перед повторной попыткой
                        else:
                            debug_logger.error(f"Не удалось отправить сообщение после {max_retries} попыток: {e}")
                            # Не останавливаем выполнение, продолжаем без отправки сообщения
                
                # Получаем информацию о токене (используем расширенную версию)
                # Тоже добавляем обработку таймаутов
                result = None
                for attempt in range(max_retries):
                    try:
                        result = await get_token_info(query, update.message.chat_id, None, context)
                        debug_logger.info(f"Получен результат get_token_info: {'успешно' if result else 'ошибка или пустой результат'}")
                        break
                    except (TimedOut, NetworkError) as e:
                        if attempt < max_retries - 1:
                            debug_logger.warning(f"Таймаут при получении данных ({attempt+1}/{max_retries}): {e}")
                            await asyncio.sleep(2)  # пауза перед повторной попыткой
                        else:
                            debug_logger.error(f"Не удалось получить данные после {max_retries} попыток: {e}")
                
                # Удаляем сообщение о поиске, если оно было отправлено
                if 'msg' in locals():
                    try:
                        await msg.delete()
                        debug_logger.info(f"Сообщение о поиске удалено")
                    except Exception as e:
                        debug_logger.error(f"Не удалось удалить сообщение о поиске: {str(e)}")
                    
                # Проверяем, нужно ли выполнить автоматическую проверку всех токенов
                if token_storage.check_auto_update_needed():
                    debug_logger.info("Запуск автоматической проверки Market Cap всех токенов")
                    context.application.create_task(check_all_market_caps(context))
                    
            except Exception as e:
                debug_logger.error(f"Критическая ошибка при обработке сообщения: {str(e)}")
                debug_logger.error(traceback.format_exc())
                # Пытаемся отправить сообщение об ошибке пользователю
                for attempt in range(max_retries):
                    try:
                        await update.message.reply_text("Произошла ошибка при обработке запроса. Пожалуйста, попробуйте позже.")
                        break
                    except Exception:
                        if attempt == max_retries - 1:
                            debug_logger.error("Не удалось отправить сообщение об ошибке пользователю")
        except Exception as e:
            debug_logger.error(f"Необработанное исключение в handle_message: {str(e)}")
            debug_logger.error(traceback.format_exc())

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает ошибки, возникающие при обработке обновлений."""
    debug_logger.error(f"Произошла ошибка при обработке обновления: {context.error}")
    debug_logger.error(traceback.format_exc())

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает все callback запросы."""
    query = update.callback_query
    
    if not query:
        return
    
    try:
        # Получаем данные callback
        data = query.data
        if not data:
            await query.answer("Ошибка: данные запроса отсутствуют")
            return
        
        debug_logger.info(f"Получен callback запрос: {data}")
        
        # Обрабатываем разные типы callback
        if data.startswith("refresh:"):
            await handle_refresh_token(update, context)
        elif data == "refresh_list":
            await handle_refresh_list(update, context)
        elif data.startswith("list_page:"):
            # Обработка навигации по страницам списка токенов
            page = int(data.split(':', 1)[1])
            await handle_list_page(update, context, page)
        elif data == "generate_excel":
            await handle_generate_excel(update, context)
        # Обработчики для скрытия токенов
        elif data == "clear_all_confirm":
            await handle_clear_all_confirm(update, context)
        elif data == "clear_confirm":
            await handle_clear_confirm(update, context)
        elif data == "clear_cancel":
            await handle_clear_cancel(update, context)
        elif data.startswith("clear_selective"):
            await handle_clear_selective(update, context)
        elif data.startswith("hide_token:"):
            await handle_hide_token(update, context)
        elif data == "clear_return":
            await handle_clear_return(update, context)
        elif data == "manage_tokens":
            # Перенаправляем на меню управления токенами
            await handle_clear_return(update, context)
        elif data == "manage_hidden":
            await handle_manage_hidden(update, context)
        elif data.startswith("manage_hidden:"):
            await handle_manage_hidden(update, context)
        elif data.startswith("unhide_token:"):
            await handle_unhide_token(update, context)
        # Новые обработчики для отображения всех токенов
        elif data == "unhide_all":
            await handle_unhide_all(update, context)
        elif data == "unhide_all_confirm":
            await handle_unhide_all_confirm(update, context)
        # Обработчики для полного удаления токенов
        elif data == "delete_all_confirm":
            await handle_delete_all_confirm(update, context)
        elif data == "delete_confirm":
            await handle_delete_confirm(update, context)
        elif data.startswith("delete_selective"):
            await handle_delete_selective(update, context)
        elif data.startswith("delete_token:"):
            await handle_delete_token(update, context)
        else:
            await query.answer("Неизвестный тип запроса")
            debug_logger.warning(f"Неизвестный тип callback запроса: {data}")
            
    except Exception as e:
        debug_logger.error(f"Ошибка при обработке callback запроса: {str(e)}")
        debug_logger.error(traceback.format_exc())
        try:
            await query.answer("Произошла ошибка. Пожалуйста, попробуйте позже.")
        except Exception:
            pass

async def handle_list_page(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int) -> None:
    """Обрабатывает запрос на отображение конкретной страницы списка токенов."""
    query = update.callback_query
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    
    try:
        # Уведомляем пользователя о начале обновления
        await query.answer("Обновляю список токенов...")
        
        # Получаем все токены, исключая скрытые
        active_tokens = token_storage.get_all_tokens(include_hidden=False)
        
        if not active_tokens:
            await query.edit_message_text(
                "Нет активных токенов в списке отслеживаемых.",
                parse_mode=ParseMode.MARKDOWN
            )
            debug_logger.info("Список токенов пуст")
            return
        
        # Форматируем список токенов с пагинацией
        tokens_per_page = 10  # Отображаем по 10 токенов на странице
        message, total_pages, current_page = format_tokens_list(active_tokens, page, tokens_per_page)
        
        # Создаем кнопки навигации
        keyboard = []
        
        # Кнопки для навигации по страницам
        nav_buttons = []
        if total_pages > 1:
            if current_page > 0:
                nav_buttons.append(InlineKeyboardButton("⬅️ Предыдущая", callback_data=f"list_page:{current_page-1}"))
            
            if current_page < total_pages - 1:
                nav_buttons.append(InlineKeyboardButton("Следующая ➡️", callback_data=f"list_page:{current_page+1}"))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        # Кнопки для действий со списком
        action_buttons = [
            InlineKeyboardButton("🔄 Обновить", callback_data=f"list_page:{current_page}"),
            InlineKeyboardButton("📊 Excel отчет", callback_data="generate_excel")
        ]
        keyboard.append(action_buttons)
        
        # Кнопка для управления токенами
        keyboard.append([InlineKeyboardButton("🔍 Управление токенами", callback_data="manage_tokens")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Обновляем сообщение с актуальными данными
        try:
            await query.edit_message_text(
                message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
            debug_logger.info(f"Список токенов успешно обновлен (страница {current_page+1} из {total_pages})")
        except telegram.error.BadRequest as e:
            if "Message is too long" in str(e):
                # Если сообщение слишком длинное, уменьшаем количество токенов на странице
                tokens_per_page = 5
                message, total_pages, current_page = format_tokens_list(active_tokens, page, tokens_per_page)
                
                # Обновляем кнопки навигации
                keyboard = []
                nav_buttons = []
                
                if total_pages > 1:
                    if current_page > 0:
                        nav_buttons.append(InlineKeyboardButton("⬅️ Предыдущая", callback_data=f"list_page:{current_page-1}"))
                    
                    if current_page < total_pages - 1:
                        nav_buttons.append(InlineKeyboardButton("Следующая ➡️", callback_data=f"list_page:{current_page+1}"))
                
                if nav_buttons:
                    keyboard.append(nav_buttons)
                
                keyboard.append(action_buttons)
                keyboard.append([InlineKeyboardButton("🔍 Управление токенами", callback_data="manage_tokens")])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    message,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup,
                    disable_web_page_preview=True
                )
                debug_logger.info(f"Список токенов успешно обновлен (страница {current_page+1} из {total_pages}, уменьшено количество токенов на странице)")
            else:
                # Если произошла другая ошибка
                debug_logger.error(f"Ошибка при обновлении списка токенов: {str(e)}")
                await query.answer("Ошибка при обновлении списка. Пожалуйста, попробуйте позже.")
    except Exception as e:
        debug_logger.error(f"Ошибка при обработке запроса списка токенов: {str(e)}")
        debug_logger.error(traceback.format_exc())
        try:
            await query.answer("Произошла ошибка. Пожалуйста, попробуйте позже.")
        except Exception:
            pass

async def handle_refresh_token(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает запрос на обновление токена."""
    query = update.callback_query
    data = query.data
    token_query = data.split(':', 1)[1]
    
    debug_logger.info(f"Получен запрос на обновление для токена {token_query}")
    
    try:
        # Проверяем, не слишком ли часто обновляем
        current_time = time.time()
        stored_data = token_storage.get_token_data(token_query)
        
        if stored_data:
            last_update_time = stored_data.get('last_update_time', 0)
            if current_time - last_update_time < 5:  # Минимум 5 секунд между обновлениями
                await query.answer("Пожалуйста, подождите несколько секунд между обновлениями")
                debug_logger.info(f"Обновление для токена {token_query} отклонено: слишком частые запросы")
                return
        else:
            # Если данных о токене нет, уведомляем и возвращаемся
            await query.answer("Информация о токене недоступна. Попробуйте заново отправить запрос.")
            debug_logger.warning(f"Не найдены данные о токене {token_query} для обновления")
            return
        
        # Уведомляем пользователя о начале обновления
        await query.answer("Обновляю информацию...")
        debug_logger.info(f"Начато обновление для токена {token_query}")
        
        # Получаем информацию о токене и обновляем сообщение (используем расширенную версию)
        result = await get_token_info(
            token_query, 
            query.message.chat_id, 
            query.message.message_id, 
            context
        )
        
        # Обновляем время последнего обновления
        if stored_data and result:
            token_storage.update_token_field(token_query, 'last_update_time', current_time)
            debug_logger.info(f"Обновление для токена {token_query} успешно выполнено")
        else:
            debug_logger.warning(f"Обновление для токена {token_query} не удалось")
            
        # Проверяем, нужно ли выполнить автоматическую проверку всех токенов
        if token_storage.check_auto_update_needed():
            debug_logger.info("Запуск автоматической проверки Market Cap всех токенов")
            context.application.create_task(check_all_market_caps(context))
    except Exception as e:
        debug_logger.error(f"Ошибка при обновлении токена {token_query}: {str(e)}")
        debug_logger.error(traceback.format_exc())
        try:
            await query.answer("Произошла ошибка при обновлении. Пожалуйста, попробуйте позже.")
        except:
            pass

async def on_startup(application):
    """Выполняется при запуске бота."""
    try:
        # Устанавливаем команды для бота
        await setup_bot_commands(application)
        
        # Импортируем модифицированную функцию мониторинга из token_service
        from token_service import (
            monitor_token_market_caps, 
            send_token_stats  # Импортируем новую функцию
        )
        
        # Настраиваем планировщик задач
        if not hasattr(application, 'job_queue') or application.job_queue is None:
            from telegram.ext import JobQueue
            application.job_queue = JobQueue()
            application.job_queue.set_application(application)
        
        # Запускаем задачу мониторинга каждые 10 секунд
        application.job_queue.run_repeating(monitor_token_market_caps, interval=10, first=5)
        debug_logger.info("Настроен автоматический мониторинг маркет капа каждые 10 секунд")
        
        # Настраиваем отправку статистики для тестирования
        application.job_queue.run_repeating(send_token_stats, interval=14400, first=10)
        debug_logger.info("Настроена отправка статистики токенов каждую минуту для тестирования")
        
        # Закомментированный оригинальный код для возврата после тестирования
        # from datetime import time as dt_time
        # morning_time = dt_time(8, 0, 0)  # 08:00:00
        # application.job_queue.run_daily(send_token_stats, time=morning_time)
        # debug_logger.info("Настроена отправка статистики токенов в 08:00")
        #
        # vening_time = dt_time(20, 0, 0)  # 20:00:00
        # application.job_queue.run_daily(send_token_stats, time=evening_time)
        # debug_logger.info("Настроена отправка статистики токенов в 20:00")
        
        debug_logger.info("Инициализация бота завершена")
    except Exception as e:
        debug_logger.error(f"Ошибка при инициализации бота: {str(e)}")
        debug_logger.error(traceback.format_exc())

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отображает статистику по токенам за последние 12 часов."""
    try:
        debug_logger.info("Запрошена статистика по токенам")
        
        # Отправляем сообщение о начале формирования статистики
        wait_message = await update.message.reply_text(
            "Формирую статистику по токенам за последние 12 часов...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Импортируем функцию для отправки статистики
        from token_service import send_token_stats
        
        # Вызываем функцию для отправки статистики
        await send_token_stats(context)
        
        # Удаляем сообщение об ожидании
        try:
            await wait_message.delete()
        except Exception as e:
            debug_logger.error(f"Ошибка при удалении сообщения об ожидании: {e}")
        
        debug_logger.info("Статистика по токенам успешно отправлена")
        
    except Exception as e:
        debug_logger.error(f"Ошибка при формировании статистики: {str(e)}")
        debug_logger.error(traceback.format_exc())
        try:
            await update.message.reply_text(
                "Произошла ошибка при формировании статистики. Пожалуйста, попробуйте позже."
            )
        except Exception:
            pass

def configure_root_logger():
    """Настраивает корневой логгер для управления всеми модулями."""
    # Настройка корневого логгера
    root_logger = logging.getLogger()
    
    # Удаляем существующие обработчики
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Файловый обработчик для всех логов
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    all_log_file = f'logs/all_components_{timestamp}.log'
    all_handler = logging.FileHandler(all_log_file, encoding='utf-8')
    all_handler.setLevel(logging.INFO)
    all_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    all_handler.setFormatter(all_formatter)
    
    # Добавляем обработчик
    root_logger.addHandler(all_handler)
    root_logger.setLevel(logging.INFO)
    
    # Настройка популярных модулей
    for module_name in ['asyncio', 'telethon', 'httpx', 'telegram', 'config']:
        module_logger = logging.getLogger(module_name)
        module_logger.setLevel(getattr(logging, 'INFO'))
    
    debug_logger.info(f"Настроено логирование всех компонентов")
    debug_logger.info(f"Объединенный лог всех компонентов: {all_log_file}")

def signal_handler(sig, frame):
    """Обработчик сигнала прерывания."""
    debug_logger.info("Получен сигнал прерывания, выполняется выход...")
    print("\n[INFO] Завершение работы системы...")
     
def main():
    """Запускает бота."""
    try:
        debug_logger.info("Запуск бота начат")
        
        # Настраиваем логирование
        configure_root_logger()
        
        # Создаем приложение и передаем ему токен телеграм бота
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        debug_logger.info("Приложение создано")
        
        # Регистрируем обработчики команд
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("list", list_tokens))
        application.add_handler(CommandHandler("stats", stats_command))
        application.add_handler(CommandHandler("excel", excel_command))
        application.add_handler(CommandHandler("clear", clear_tokens))
        debug_logger.info("Обработчики команд зарегистрированы")
        
        # Регистрируем обработчик для обычных сообщений
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        # Регистрируем обработчик для инлайн-кнопок
        application.add_handler(CallbackQueryHandler(handle_callback))
        
        # Регистрируем обработчик ошибок
        application.add_error_handler(error_handler)
        debug_logger.info("Обработчики событий зарегистрированы")
        
        # Добавляем функцию, которая выполнится при запуске бота
        application.post_init = on_startup
        
        # Устанавливаем команды меню напрямую
        setup_commands_direct(TELEGRAM_TOKEN)
        debug_logger.info("Команды меню установлены")
        
        # Запускаем бота - СИНХРОННЫЙ блокирующий вызов
        debug_logger.info("Бот запущен и готов к работе")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
            
    except Exception as e:
        debug_logger.error(f"Критическая ошибка при запуске бота: {str(e)}")
        debug_logger.error(traceback.format_exc())
        print(f"Критическая ошибка при запуске бота: {str(e)}")
        print("Подробности смотрите в файле logs/debug.log")
# Эта глобальная обертка нужна для отслеживания всех необработанных исключений
if __name__ == "__main__":
    try:
        print("Запуск бота для отслеживания токенов...")
        print("Логи отладки будут сохранены в файл logs/debug.log")
        debug_logger.info("=" * 50)
        debug_logger.info("ЗАПУСК ПРИЛОЖЕНИЯ")
        debug_logger.info("=" * 50)
        
        # Импортируем requests здесь для проверки наличия и версии
        import requests
        debug_logger.info(f"Версия библиотеки requests: {requests.__version__}")
        
        # Проверяем, есть ли необходимые библиотеки
        import sys
        debug_logger.info(f"Версия Python: {sys.version}")
        
        # Проверяем наличие необходимых модулей
        required_modules = ["telegram", "token_storage", "utils", "token_service"]
        for module in required_modules:
            try:
                __import__(module)
                debug_logger.info(f"Модуль {module} успешно импортирован")
            except ImportError as e:
                debug_logger.error(f"Не удалось импортировать модуль {module}: {str(e)}")
                print(f"Ошибка: не удалось импортировать модуль {module}")
                sys.exit(1)
        
        # Запускаем основную функцию напрямую, без asyncio.run()
        main()
    except Exception as e:
        debug_logger.critical(f"Необработанное исключение в главном блоке: {str(e)}")
        debug_logger.critical(traceback.format_exc())
        print(f"Критическая ошибка: {str(e)}")
        print("Подробности смотрите в файле logs/debug.log")