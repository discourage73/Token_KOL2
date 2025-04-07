import logging
import time
from typing import Dict, Any, Optional, List

# Настройка логгирования
logger = logging.getLogger(__name__)

# Словарь для хранения данных о токенах
# Ключ: запрос пользователя (адрес или название токена)
# Значение: словарь с данными о токене
token_data_store: Dict[str, Dict[str, Any]] = {}

# Интервал для автоматической проверки токенов (в секундах)
AUTO_CHECK_INTERVAL = 60  # 1 минута

# Время последней автоматической проверки
last_auto_check_time = 0

# Период хранения токенов (в секундах)
TOKEN_RETENTION_PERIOD = 86400  # 24 часа

# Словарь для хранения ID сообщений со списками токенов для каждого чата
list_message_ids = {}

def store_token_data(query: str, data: Dict[str, Any]) -> None:
    """Сохраняет данные о токене в хранилище."""
    # Добавляем время добавления токена, если его нет
    if 'added_time' not in data:
        data['added_time'] = time.time()
    
    token_data_store[query] = data
    logger.info(f"Данные о токене '{query}' сохранены в хранилище")

def get_token_data(query: str) -> Optional[Dict[str, Any]]:
    """Получает данные о токене из хранилища."""
    data = token_data_store.get(query)
    if data:
        logger.info(f"Данные о токене '{query}' получены из хранилища")
    else:
        logger.info(f"Данные о токене '{query}' не найдены в хранилище")
    return data

def update_token_field(query: str, field: str, value: Any) -> bool:
    """Обновляет значение поля в данных о токене."""
    if query in token_data_store:
        token_data_store[query][field] = value
        logger.info(f"Поле '{field}' для токена '{query}' обновлено на значение '{value}'")
        return True
    else:
        logger.warning(f"Не удалось обновить поле '{field}' для токена '{query}': токен не найден")
        return False

def remove_token_data(query: str) -> bool:
    """Удаляет данные о токене из хранилища."""
    if query in token_data_store:
        del token_data_store[query]
        logger.info(f"Данные о токене '{query}' удалены из хранилища")
        return True
    else:
        logger.warning(f"Не удалось удалить данные о токене '{query}': токен не найден")
        return False

def get_all_tokens() -> Dict[str, Dict[str, Any]]:
    """Возвращает словарь со всеми отслеживаемыми токенами."""
    return token_data_store

def get_active_tokens() -> Dict[str, Dict[str, Any]]:
    """Возвращает словарь с токенами, добавленными за последние 24 часа."""
    current_time = time.time()
    active_tokens = {}
    
    for query, data in token_data_store.items():
        added_time = data.get('added_time', 0)
        if current_time - added_time <= TOKEN_RETENTION_PERIOD:
            active_tokens[query] = data
    
    return active_tokens

def update_token_ath(query: str, current_mcap: float) -> bool:
    """Обновляет ATH (All-Time High) маркет капа токена, если текущее значение выше."""
    if query not in token_data_store:
        return False
    
    current_ath = token_data_store[query].get('ath_market_cap', 0)
    
    if current_mcap > current_ath:
        token_data_store[query]['ath_market_cap'] = current_mcap
        token_data_store[query]['ath_time'] = time.time()
        logger.info(f"Обновлен ATH для токена '{query}': {current_mcap}")
        return True
    
    return False

def check_auto_update_needed() -> bool:
    """Проверяет, нужно ли выполнить автоматическую проверку токенов."""
    global last_auto_check_time
    current_time = time.time()
    
    if current_time - last_auto_check_time >= AUTO_CHECK_INTERVAL:
        last_auto_check_time = current_time
        return True
    
    return False

def update_last_auto_check_time() -> None:
    """Обновляет время последней автоматической проверки."""
    global last_auto_check_time
    last_auto_check_time = time.time()

def clear_all_tokens() -> None:
    """Полностью очищает хранилище токенов."""
    global token_data_store
    token_count = len(token_data_store)
    token_data_store = {}
    logger.info(f"Все данные о токенах ({token_count} шт.) очищены вручную")
    
    return token_count

def clean_expired_tokens() -> List[str]:
    """Удаляет токены, которые находятся в хранилище более 24 часов.
    Возвращает список удаленных токенов."""
    current_time = time.time()
    expired_tokens = []
    
    for query, data in list(token_data_store.items()):
        added_time = data.get('added_time', 0)
        if current_time - added_time > TOKEN_RETENTION_PERIOD:
            del token_data_store[query]
            expired_tokens.append(query)
            logger.info(f"Токен '{query}' удален из-за истечения срока хранения (24 часа)")
    
    return expired_tokens
def store_list_message_id(chat_id: int, message_id: int) -> None:
    """Сохраняет ID сообщения со списком токенов для указанного чата."""
    list_message_ids[chat_id] = message_id
    logger.info(f"ID сообщения со списком токенов для чата {chat_id} сохранен: {message_id}")

def get_list_message_id(chat_id: int) -> Optional[int]:
    """Получает ID последнего сообщения со списком токенов для указанного чата."""
    message_id = list_message_ids.get(chat_id)
    return message_id