import datetime
import logging
import time
from typing import Dict, Any, Optional, Union, List

logger = logging.getLogger(__name__)

def format_number(value: Union[int, float, str]) -> str:
    """Форматирует числовое значение для отображения."""
    if isinstance(value, (int, float)):
        if value >= 1000000000:
            return f"${value / 1000000000:.2f}B"
        elif value >= 1000000:
            return f"${value / 1000000:.2f}M"
        elif value >= 1000:
            return f"${value / 1000:.2f}K"
        else:
            return f"${value:.2f}"
    elif isinstance(value, str):
        try:
            value = float(value)
            return format_number(value)
        except (ValueError, TypeError):
            return value
    else:
        return "Неизвестно"

def calculate_token_age(timestamp: Optional[int]) -> str:
    """Рассчитывает возраст токена от времени создания с детальной разбивкой."""
    if not timestamp:
        return "Неизвестно"
    
    try:
        # Преобразование timestamp из миллисекунд в секунды
        creation_time = datetime.datetime.fromtimestamp(timestamp / 1000)
        now = datetime.datetime.now()
        delta = now - creation_time
        
        days = delta.days
        hours = delta.seconds // 3600
        minutes = (delta.seconds % 3600) // 60
        
        result = []
        
        if days > 0:
            days_str = "день" if days == 1 else "дня" if 1 < days < 5 else "дней"
            result.append(f"{days} {days_str}")
        
        if hours > 0:
            hours_str = "час" if hours == 1 else "часа" if 1 < hours < 5 else "часов"
            result.append(f"{hours} {hours_str}")
        
        if minutes > 0 and days == 0:  # Показываем минуты только если прошло меньше дня
            minutes_str = "минута" if minutes == 1 else "минуты" if 1 < minutes < 5 else "минут"
            result.append(f"{minutes} {minutes_str}")
        
        if not result:
            return "Менее минуты"
        
        return " ".join(result)
    except Exception as e:
        logger.error(f"Ошибка при расчете возраста токена: {e}")
        return "Неизвестно"

def time_elapsed_since(timestamp: float) -> str:
    """Вычисляет прошедшее время с указанного момента."""
    if not timestamp:
        return "Неизвестно"
    
    try:
        now = time.time()
        delta_seconds = now - timestamp
        
        # Преобразуем в timedelta для удобства расчета
        delta = datetime.timedelta(seconds=delta_seconds)
        
        days = delta.days
        hours = delta.seconds // 3600
        minutes = (delta.seconds % 3600) // 60
        
        result = []
        
        if days > 0:
            days_str = "день" if days == 1 else "дня" if 1 < days < 5 else "дней"
            result.append(f"{days} {days_str}")
        
        if hours > 0:
            hours_str = "час" if hours == 1 else "часа" if 1 < hours < 5 else "часов"
            result.append(f"{hours} {hours_str}")
        
        if minutes > 0 and days == 0:  # Показываем минуты только если прошло меньше дня
            minutes_str = "минута" if minutes == 1 else "минуты" if 1 < minutes < 5 else "минут"
            result.append(f"{minutes} {minutes_str}")
        
        if not result:
            return "Менее минуты"
        
        return " ".join(result)
    except Exception as e:
        logger.error(f"Ошибка при расчете прошедшего времени: {e}")
        return "Неизвестно"

def process_token_data(token_data: Dict[str, Any]) -> Dict[str, Any]:
    """Обрабатывает данные о токене."""
    # Извлекаем нужную информацию
    base_token = token_data.get('baseToken', {})
    ticker = base_token.get('symbol', 'Неизвестно').upper()
    ticker_address = base_token.get('address', 'Неизвестно')
    pair_address = token_data.get('pairAddress', '')
    chain_id = token_data.get('chainId', '')
    
    # Получаем market cap, если доступно
    market_cap = token_data.get('fdv')
    raw_market_cap = market_cap  # Сохраняем исходное значение
    market_cap_formatted = format_number(market_cap)
    
    # Создаем ссылки
    dexscreener_link = f"https://dexscreener.com/{chain_id}/{pair_address}"
    axiom_link = f"https://axiom.trade/meme/{pair_address}"
    
    # Получаем объем торгов
    volume_data = token_data.get('volume', {})
    volume_5m = volume_data.get('m5')
    volume_1h = volume_data.get('h1')
    
    # Форматируем объемы
    volume_5m_formatted = format_number(volume_5m)
    volume_1h_formatted = format_number(volume_1h)
    
    # Получаем время создания токена
    pair_created_at = token_data.get('pairCreatedAt')
    token_age = calculate_token_age(pair_created_at)
    
    # Получаем информацию о социальных сетях и сайтах
    info = token_data.get('info', {})
    websites = info.get('websites', [])
    socials = info.get('socials', [])
    
    return {
        'ticker': ticker,
        'ticker_address': ticker_address,
        'pair_address': pair_address,
        'chain_id': chain_id,
        'market_cap': market_cap_formatted,
        'raw_market_cap': raw_market_cap,
        'volume_5m': volume_5m_formatted,
        'volume_1h': volume_1h_formatted,
        'token_age': token_age,
        'dexscreener_link': dexscreener_link,
        'axiom_link': axiom_link,
        'websites': websites,
        'socials': socials
    }

def format_message(token_info: Dict[str, Any], initial_data: Optional[Dict[str, Any]] = None) -> str:
    """Форматирует сообщение с информацией о токене."""
    message = f"🪙 *Тикер*: {token_info['ticker']}\n"
    message += f"📝 *Адрес*: `{token_info['ticker_address']}`\n\n"
    
    message += f"💰 *Market Cap*: {token_info['market_cap']}\n"
    
    # Проверяем изменение маркет капа, если есть начальные данные
    if (initial_data and 'raw_market_cap' in initial_data and 
        initial_data['raw_market_cap'] and token_info['raw_market_cap']):
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
    
    message += f"⏱ *Возраст токена*: {token_info['token_age']}\n\n"
    
    # Блок с объемами торгов
    volumes_block = ""
    if token_info['volume_5m'] != "Неизвестно":
        volumes_block += f"📈 *Объем (5м)*: {token_info['volume_5m']}\n"
        
    if token_info['volume_1h'] != "Неизвестно":
        volumes_block += f"📈 *Объем (1ч)*: {token_info['volume_1h']}\n"
    
    if volumes_block:
        message += volumes_block + "\n"
    
    # Блок с ссылками на торговые площадки
    message += f"🔎 *Ссылки*: [DexScreener]({token_info['dexscreener_link']}) | [Axiom Trade]({token_info['axiom_link']})\n\n"
    
    # Блок с ссылками на сайты
    if token_info['websites']:
        website_links = [f"[{website.get('label', 'Website')}]({website.get('url', '')})" 
                         for website in token_info['websites'] if website.get('url')]
        
        if website_links:
            message += f"🌐 *Сайты*: {' | '.join(website_links)}\n"
    
    # Блок с ссылками на соцсети
    if token_info['socials']:
        social_links = [f"[{social.get('type', '').capitalize()}]({social.get('url', '')})" 
                        for social in token_info['socials'] if social.get('url') and social.get('type')]
        
        if social_links:
            message += f"📱 *Соцсети*: {' | '.join(social_links)}\n"
    
    # Добавляем метку времени и исходные данные
    current_time = datetime.datetime.now().strftime("%H:%M:%S")
    message += f"\n_Обновлено: {current_time}_"
    
    # Добавляем информацию о первоначальном запросе, если она доступна
    if initial_data:
        message += f"\n_Первый запрос: {initial_data['time']}_"
        message += f"\n_Начальный Market Cap: {initial_data['market_cap']}_"
    
    return message

def remove_specific_token(token_storage, token_query: str):
    """
    Удаляет указанный токен из хранилища.
    
    Args:
        token_storage: Модуль хранения токенов
        token_query: Запрос или тикер токена для удаления
    
    Returns:
        dict: Информация об удаленном токене или None, если токен не найден
    """
    # Сначала получаем все токены
    all_tokens = token_storage.get_all_tokens()
    
    # Ищем точное совпадение по запросу/адресу
    if token_query in all_tokens:
        token_data = all_tokens[token_query]
        token_storage.remove_token_data(token_query)
        return {"query": token_query, "data": token_data}
    
    # Если точного совпадения нет, ищем по тикеру (нечувствительно к регистру)
    for query, data in all_tokens.items():
        ticker = ""
        if 'token_info' in data and 'ticker' in data['token_info']:
            ticker = data['token_info']['ticker']
        
        # Проверяем совпадение тикера (нечувствительно к регистру)
        if ticker.lower() == token_query.lower():
            token_data = all_tokens[query]
            token_storage.remove_token_data(query)
            return {"query": query, "data": token_data}
    
    # Если токен не найден
    return None

def format_tokens_list(tokens_data: Dict[str, Dict[str, Any]], page: int = 0, tokens_per_page: int = 10) -> tuple:
    """
    Форматирует список токенов для отображения с процентами от ATH.
    Возвращает кортеж (message, total_pages, current_page)
    """
    if not tokens_data:
        return ("Нет активных токенов в списке отслеживаемых.", 1, 0)
    
    # Получаем количество скрытых токенов для информации
    hidden_info = ""
    try:
        # Импортируем модуль token_storage, если он еще не импортирован
        import token_storage as ts
        hidden_tokens_count = len(ts.get_hidden_tokens())
        hidden_info = f" (скрытых: {hidden_tokens_count})" if hidden_tokens_count > 0 else ""
    except Exception as e:
        logger.error(f"Ошибка при получении скрытых токенов: {str(e)}")
    
    # Подготавливаем данные токенов для сортировки
    token_info_list = []
    
    try:
        for query, data in tokens_data.items():
            # Пропускаем скрытые токены
            if data.get('hidden', False):
                continue
                
            # Безопасно получаем данные с проверками на None
            token_info = {}
            token_info['query'] = query
            
            # Получаем тикер
            token_info['ticker'] = query
            if data.get('token_info', {}).get('ticker'):
                token_info['ticker'] = data['token_info']['ticker']
            
            # Получаем время добавления и преобразуем его в полную дату и время
            token_info['initial_time'] = "Неизвестно"
            token_info['added_date'] = ""
            
            if data.get('added_time'):
                # Преобразуем timestamp в дату и время
                import datetime
                added_datetime = datetime.datetime.fromtimestamp(data.get('added_time', 0))
                token_info['initial_time'] = added_datetime.strftime("%H:%M:%S")
                token_info['added_date'] = added_datetime.strftime("%Y-%m-%d")
                token_info['full_datetime'] = added_datetime.strftime("%Y-%m-%d %H:%M:%S")
            elif data.get('initial_data', {}).get('time'):
                token_info['initial_time'] = data['initial_data']['time']
            
            # Получаем начальный маркет кап
            token_info['initial_market_cap'] = 0
            if data.get('initial_data', {}).get('raw_market_cap'):
                token_info['initial_market_cap'] = data['initial_data']['raw_market_cap']
            
            # Получаем текущий маркет кап
            token_info['current_market_cap'] = 0
            if data.get('token_info', {}).get('raw_market_cap'):
                token_info['current_market_cap'] = data['token_info']['raw_market_cap']
            
            # Получаем ATH маркет кап
            token_info['ath_market_cap'] = data.get('ath_market_cap', 0)
            
            # Если ATH не установлен или меньше начального, используем начальный как ATH
            if not token_info['ath_market_cap'] or (token_info['initial_market_cap'] > token_info['ath_market_cap']):
                token_info['ath_market_cap'] = token_info['initial_market_cap']
            
            # Безопасно вычисляем проценты для ATH и текущего значения
            token_info['ath_percent'] = 0
            if token_info['initial_market_cap'] and token_info['ath_market_cap'] and token_info['initial_market_cap'] > 0:
                token_info['ath_percent'] = ((token_info['ath_market_cap'] / token_info['initial_market_cap']) - 1) * 100
            
            token_info['curr_percent'] = 0
            if token_info['initial_market_cap'] and token_info['current_market_cap'] and token_info['initial_market_cap'] > 0:
                token_info['curr_percent'] = ((token_info['current_market_cap'] / token_info['initial_market_cap']) - 1) * 100
            
            # Получаем ссылку на DexScreener
            token_info['dexscreener_link'] = "#"
            if data.get('token_info', {}).get('dexscreener_link'):
                token_info['dexscreener_link'] = data['token_info']['dexscreener_link']
            
            token_info_list.append(token_info)
        
        # Сортируем токены по проценту роста ATH (от наибольшего к наименьшему)
        token_info_list.sort(key=lambda x: x.get('ath_percent', 0), reverse=True)
    except Exception as e:
        logger.error(f"Ошибка при подготовке данных токенов: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return ("Произошла ошибка при формировании списка токенов. Пожалуйста, попробуйте позже.", 1, 0)
    
    # Расчет количества страниц
    total_tokens = len(token_info_list)
    total_pages = (total_tokens + tokens_per_page - 1) // tokens_per_page  # Округление вверх
    
    # Проверка валидности номера страницы
    if page < 0:
        page = 0
    elif page >= total_pages and total_pages > 0:
        page = total_pages - 1
    
    # Начало и конец диапазона токенов для текущей страницы
    start_idx = page * tokens_per_page
    end_idx = min(start_idx + tokens_per_page, total_tokens)
    
    # Токены для текущей страницы
    page_tokens = token_info_list[start_idx:end_idx]
    
    # Заголовок сообщения
    message = f"📋 *Список отслеживаемых токенов ({total_tokens} шт.){hidden_info}*\n"
    message += f"Страница {page + 1} из {total_pages}\n\n"
    
    # Загрузим tracker_db для получения эмодзи токенов
    tracker_emojis = {}
    try:
        import json
        import os
        
        # Загружаем JSON файл tracker_db для получения эмодзи
        if os.path.exists('tokens_tracker_database.json'):
            with open('tokens_tracker_database.json', 'r', encoding='utf-8') as f:
                tracker_db = json.load(f)
                
            # Сохраняем эмодзи из tracker_db
            for token_query, token_data in tracker_db.items():
                if 'emojis' in token_data:
                    tracker_emojis[token_query] = token_data['emojis']
    except Exception as e:
        logger.error(f"Ошибка при загрузке эмодзи из tracker_db: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
    
    # Форматируем список токенов для текущей страницы
    try:
        for i, token in enumerate(page_tokens, start=start_idx + 1):
            ticker = token.get('ticker', 'Неизвестно')
            query = token.get('query', '')
            
            # Получаем полную дату и время
            if token.get('full_datetime'):
                date_time_str = token.get('full_datetime')
            else:
                added_date = token.get('added_date', '')
                initial_time = token.get('initial_time', 'Неизвестно')
                date_time_str = f"{added_date} {initial_time}" if added_date else initial_time
            
            dexscreener_link = token.get('dexscreener_link', '#')
            
            # Безопасное форматирование чисел
            initial_mc = format_number(token.get('initial_market_cap', 0)) if token.get('initial_market_cap') else "Неизвестно"
            current_mc = format_number(token.get('current_market_cap', 0)) if token.get('current_market_cap') else "Неизвестно"
            ath_mc = format_number(token.get('ath_market_cap', 0)) if token.get('ath_market_cap') else "Неизвестно"
            
            # Форматируем проценты для ATH и текущего значения
            ath_percent = token.get('ath_percent', 0)
            curr_percent = token.get('curr_percent', 0)
            
            ath_percent_str = f"+{ath_percent:.1f}%" if ath_percent >= 0 else f"{ath_percent:.1f}%"
            curr_percent_str = f"+{curr_percent:.1f}%" if curr_percent >= 0 else f"{curr_percent:.1f}%"
            
            # Получаем эмодзи для токена из tracker_db
            emojis = tracker_emojis.get(query, "")
            
            # Добавляем информацию о токене в сообщение со ссылкой в названии тикера
            message += f"{i}. [{ticker}]({dexscreener_link}):\n"
            message += f"   Time: {date_time_str} Mcap: {initial_mc}\n"
            message += f"   {ath_percent_str} ATH {ath_mc}\n"
            message += f"   {curr_percent_str} CURR {current_mc}\n"
            
            # Добавляем строку эмодзи после строки с CURR, если они есть
            if emojis:
                message += f"   {emojis}\n"
            
            message += "\n"
    except Exception as e:
        logger.error(f"Ошибка при форматировании списка токенов: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return ("Произошла ошибка при форматировании списка токенов. Пожалуйста, попробуйте позже.", 1, 0)
    
    # Добавляем информацию о командах
    if page == total_pages - 1:  # Только на последней странице
        message += f"Используйте `/clear` для управления токенами.\n"
        message += f"Отправьте `/excel` для формирования Excel файла со всеми данными."
    
    return (message, total_pages, page)

def format_growth_message(ticker: str, current_multiplier: int, market_cap: str) -> str:
    """Форматирует сообщение о росте токена с огоньками по количеству множителя."""
    fire_emojis = "🔥" * current_multiplier
    
    return (
        f"{fire_emojis}\n"
        f"Токен *{ticker}* вырос в *{current_multiplier}x* от начального значения!\n\n"
        f"💰 Текущий Market Cap: {market_cap}"
    )