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

def format_tokens_list(tokens_data: Dict[str, Dict[str, Any]]) -> str:
    """Форматирует список токенов для отображения."""
    if not tokens_data:
        return "Нет активных токенов за последние 24 часа."
    
    message = f"📋 *Список отслеживаемых токенов ({len(tokens_data)} шт.)*\n\n"
    
    # Подготавливаем данные токенов
    growing_tokens = []
    falling_tokens = []
    
    for query, data in tokens_data.items():
        # Получаем начальный маркет кап
        initial_market_cap = 0
        if 'initial_data' in data and 'raw_market_cap' in data['initial_data']:
            initial_market_cap = data['initial_data'].get('raw_market_cap', 0)
        
        # Получаем текущий маркет кап из token_info, если он есть
        current_market_cap = 0
        if 'token_info' in data and 'raw_market_cap' in data['token_info']:
            current_market_cap = data['token_info'].get('raw_market_cap', 0)
        
        # Используем ATH маркет кап из хранилища
        ath_market_cap = data.get('ath_market_cap', 0)
        
        # Если ATH не установлен или меньше начального, используем начальный как ATH
        if not ath_market_cap or (initial_market_cap > ath_market_cap):
            ath_market_cap = initial_market_cap
        
        # Вычисляем максимальный множитель роста от начального до ATH
        max_multiplier = 1
        if initial_market_cap and ath_market_cap and initial_market_cap > 0:
            max_multiplier = ath_market_cap / initial_market_cap
        
        # Вычисляем текущий процент относительно начального маркет капа
        current_multiplier = 1
        if initial_market_cap and current_market_cap and initial_market_cap > 0:
            current_multiplier = current_market_cap / initial_market_cap
        
        # Получаем тикер из информации о токене
        ticker = query
        if 'token_info' in data and 'ticker' in data['token_info']:
            ticker = data['token_info'].get('ticker', query)
        
        # Получаем ссылку на DexScreener
        dexscreener_link = "#"  # Значение по умолчанию
        if 'token_info' in data and 'dexscreener_link' in data['token_info']:
            dexscreener_link = data['token_info'].get('dexscreener_link', "#")
        
        # Информация о токене
        token_info = {
            'query': query,
            'ticker': ticker,
            'initial_market_cap': initial_market_cap,
            'market_cap': current_market_cap,
            'ath_market_cap': ath_market_cap,
            'max_multiplier': max_multiplier,
            'current_multiplier': current_multiplier,
            'dexscreener_link': dexscreener_link,
            # Вычисляем процент падения от начального значения, если есть
            'decline_percent': 0 if current_multiplier >= 1 else (1 - current_multiplier) * 100
        }
        
        # Распределяем токены на растущие и падающие
        if current_multiplier >= 1:
            growing_tokens.append(token_info)
        else:
            falling_tokens.append(token_info)
    
    # Сортируем растущие токены по убыванию множителя
    growing_tokens.sort(key=lambda x: x['max_multiplier'], reverse=True)
    
    # Сортируем падающие токены по возрастанию процента падения (от меньшей потери к большей)
    falling_tokens.sort(key=lambda x: x['decline_percent'])
    
    # Форматируем растущие токены
    for i, token in enumerate(growing_tokens, 1):
        ticker = token['ticker']
        current_mc = format_number(token['market_cap']) if token['market_cap'] else "Неизвестно"
        ath_mc = format_number(token['ath_market_cap']) if token['ath_market_cap'] else "Неизвестно"
        dexscreener_link = token['dexscreener_link']
        
        # Форматируем максимальный множитель роста
        max_mult = token['max_multiplier']
        
        # Форматируем множитель
        if max_mult >= 2:
            # Если максимальный множитель больше или равен 2, показываем как "xN"
            growth_mult_str = f"x{int(max_mult)}" if max_mult >= 10 else f"x{max_mult:.1f}"
        else:
            # Если максимальный множитель меньше 2, показываем как "+N%"
            growth_percent = (max_mult - 1) * 100
            growth_mult_str = f"+{growth_percent:.1f}%"
        
        # Основная строка с информацией о токене в порядке: множитель | ATH | CURR
        token_line = f"{i}. [*{ticker}*]({dexscreener_link}): {growth_mult_str}"
        
        # Добавляем ATH маркет кап
        token_line += f" | ATH {ath_mc}"
        
        # Добавляем текущий маркет кап
        token_line += f" | CURR {current_mc}"
        
        message += token_line + "\n"
    
    # Добавляем разделитель, если есть и растущие, и падающие токены
    if growing_tokens and falling_tokens:
        message += "\n"  # Пустая строка как разделитель
    
    # Форматируем падающие токены
    for i, token in enumerate(falling_tokens, len(growing_tokens) + 1):
        ticker = token['ticker']
        current_mc = format_number(token['market_cap']) if token['market_cap'] else "Неизвестно"
        ath_mc = format_number(token['ath_market_cap']) if token['ath_market_cap'] else "Неизвестно"
        dexscreener_link = token['dexscreener_link']
        
        # Форматируем процент падения
        decline_percent = token['decline_percent']
        decline_str = f"-{decline_percent:.1f}%"
        
        # Основная строка с информацией о токене в порядке: падение | ATH | CURR
        token_line = f"{i}. [*{ticker}*]({dexscreener_link}): {decline_str}"
        
        # Добавляем ATH маркет кап
        token_line += f" | ATH {ath_mc}"
        
        # Добавляем текущий маркет кап
        token_line += f" | CURR {current_mc}"
        
        message += token_line + "\n"
    
        message += "\n_Отправьте_ `/delete ТИКЕР` _для удаления токена из списка._"
    
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