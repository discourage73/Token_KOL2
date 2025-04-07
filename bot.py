import os
import logging
import time
import asyncio
from typing import Dict, Any, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
from telegram.error import TimedOut, NetworkError

# Импортируем модули проекта
import token_storage
from config import TELEGRAM_TOKEN, logger
from token_service import get_token_info, process_token_address, check_all_tokens_growth, check_all_market_caps, check_market_cap_only
from utils import format_number, format_tokens_list, remove_specific_token



async def extract_token_address_from_message(text: str) -> str:
    """Извлекает адрес контракта токена из сообщения.
    
    Поддерживает форматы:
    - Обычный текст с адресом
    - Пересланные сообщения с адресом в формате "Контракт: [адрес]"
    - Адреса токенов Ethereum/BSC (0x...)
    - Адреса токенов Solana (от 32 до 44 символов)
    
    Returns:
        str: Адрес контракта токена или пустая строка, если адрес не найден.
    """
    import re
    
    # Шаблоны для поиска адреса контракта
    patterns = [
        # Формат "Контракт: [адрес]" для Ethereum/BSC
        r'(?:Контракт|Contract):\s*([0-9a-zA-Z]{42})',
        # Формат "Контракт: [адрес]" для Solana 
        r'(?:Контракт|Contract):\s*([a-zA-Z0-9]{32,44})',
        # Ethereum/BSC адрес
        r'0x[0-9a-fA-F]{40}',
        # Solana адрес токена (32-44 символа, обычно начинаются с буквы)
        r'\b[a-zA-Z0-9]{32,44}\b'
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text)
        if matches:
            for match in matches:
                # Проверяем, что это не рандомный текст, а похож на адрес токена
                # Для Solana - проверяем минимальную длину и содержание символов
                if match.startswith('0x') or (len(match) >= 32 and bool(re.match(r'^[a-zA-Z0-9]+$', match))):
                    logger.info(f"Найден адрес контракта в сообщении: {match}")
                    return match
    
    logger.warning("Адрес контракта не найден в сообщении")
    return ""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет приветственное сообщение при команде /start."""
    try:
        await update.message.reply_text(
            "Привет! Я предоставляю информацию о криптотокенах.\n\n"
            "Отправь мне адрес токена или его название, и я покажу тебе информацию о нем.\n\n"
            "Доступные команды:\n"
            "/start - запустить бота\n"
            "/stop - остановить бота\n"
            "/help - показать справку\n"
            "/list - показать список отслеживаемых токенов\n"
            "/clear - очистить все данные о токенах\n"
            "/delete ТИКЕР - удалить токен из списка отслеживаемых"
        )
    except (TimedOut, NetworkError) as e:
        logger.error(f"Таймаут при отправке сообщения /start: {e}")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет сообщение об остановке бота при команде /stop."""
    try:
        await update.message.reply_text(
            "Бот остановлен. Чтобы начать работу снова, отправьте команду /start."
        )
    except (TimedOut, NetworkError) as e:
        logger.error(f"Таймаут при отправке сообщения /stop: {e}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет справочное сообщение при команде /help."""
    try:
        await update.message.reply_text(
            "Я могу предоставить информацию о токенах.\n\n"
            "Просто отправь мне адрес контракта или название токена, и я покажу тебе его данные.\n"
            "Я также отслеживаю рост Market Cap и отправляю уведомления при значительном росте (x2, x3, x4...).\n\n"
            "Доступные команды:\n"
            "/start - запустить бота\n"
            "/stop - остановить бота\n"
            "/help - показать справку\n"
            "/list - показать список отслеживаемых токенов\n"
            "/clear - очистить все данные о токенах\n"
            "/delete ТИКЕР - удалить токен из списка отслеживаемых"
        )
    except (TimedOut, NetworkError) as e:
        logger.error(f"Таймаут при отправке сообщения /help: {e}")

async def list_tokens(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает список всех отслеживаемых токенов за последние 24 часа."""
    try:
        logger.info("Запрошен список отслеживаемых токенов")
        
        # Очищаем устаревшие токены перед формированием списка
        expired_tokens = token_storage.clean_expired_tokens()
        if expired_tokens:
            logger.info(f"Удалено {len(expired_tokens)} устаревших токенов")
        
        # Получаем chat_id для идентификации чата
        chat_id = update.message.chat_id
        
        # Проверяем, есть ли предыдущее сообщение со списком токенов для этого чата
        prev_message_id = token_storage.get_list_message_id(chat_id)
        
        # Удаляем команду /list пользователя (если бот имеет права на удаление сообщений)
        try:
            await update.message.delete()
            logger.info(f"Команда /list удалена из чата {chat_id}")
        except Exception as e:
            logger.warning(f"Не удалось удалить команду /list: {e}")
        
        # Если есть предыдущее сообщение, удаляем его
        if prev_message_id:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=prev_message_id)
                logger.info(f"Предыдущее сообщение со списком токенов удалено (ID: {prev_message_id})")
            except Exception as e:
                logger.warning(f"Не удалось удалить предыдущее сообщение: {e}")
        
        # Отправляем новое сообщение с уведомлением об обновлении данных
        wait_message = await context.bot.send_message(
            chat_id=chat_id,
            text="Обновляю данные о токенах...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Сохраняем ID нового сообщения
        token_storage.store_list_message_id(chat_id, wait_message.message_id)
        
        # Получаем активные токены (последние 24 часа)
        active_tokens = token_storage.get_active_tokens()
        
        if not active_tokens:
            await wait_message.edit_text(
                "Нет активных токенов за последние 24 часа."
            )
            return
        
        # Обновляем Market Cap для всех токенов перед отображением
        for query in list(active_tokens.keys()):
            try:
                # Короткая пауза между запросами
                await asyncio.sleep(0.5)
                await check_market_cap_only(query, chat_id, context)
            except Exception as e:
                logger.error(f"Ошибка при обновлении Market Cap для токена {query}: {e}")
        
        # Получаем свежие данные о токенах после обновления
        active_tokens = token_storage.get_active_tokens()
        
        # Форматируем список токенов
        message = format_tokens_list(active_tokens)
        
        # Обновляем сообщение с актуальными данными
        await wait_message.edit_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        logger.info(f"Список из {len(active_tokens)} токенов успешно отправлен")
        
    except (TimedOut, NetworkError) as e:
        logger.error(f"Таймаут при отправке списка токенов: {e}")
        try:
            await update.message.reply_text(
                "Произошла ошибка при формировании списка токенов. Пожалуйста, попробуйте позже."
            )
        except:
            pass
    except Exception as e:
        logger.error(f"Ошибка при выполнении команды /list: {e}")
        try:
            await update.message.reply_text(
                "Произошла ошибка при обработке запроса. Пожалуйста, попробуйте позже."
            )
        except:
            pass

async def clear_tokens(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Очищает все данные о токенах по запросу пользователя."""
    try:
        logger.info("Запрошена очистка всех данных о токенах")
        
        # Получаем словарь со всеми токенами
        all_tokens = token_storage.get_all_tokens()
        tokens_count = len(all_tokens)
        
        if tokens_count == 0:
            await update.message.reply_text(
                "Нет сохраненных токенов для очистки."
            )
            return
        
        # Создаем кнопки для подтверждения
        keyboard = [
            [
                InlineKeyboardButton("✅ Да, очистить все", callback_data="clear_confirm"),
                InlineKeyboardButton("❌ Отмена", callback_data="clear_cancel")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Отправляем сообщение с запросом подтверждения
        await update.message.reply_text(
            f"Вы уверены, что хотите удалить *все* данные о токенах? ({tokens_count} шт.)\n\n"
            "Это действие нельзя отменить.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        logger.info(f"Отправлен запрос подтверждения очистки {tokens_count} токенов")
        
    except Exception as e:
        logger.error(f"Ошибка при выполнении команды /clear: {e}")
        try:
            await update.message.reply_text(
                "Произошла ошибка при обработке запроса. Пожалуйста, попробуйте позже."
            )
        except:
            pass

async def delete_token_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /delete для удаления конкретного токена."""
    try:
        # Проверяем, есть ли аргументы команды
        if not context.args:
            await update.message.reply_text(
                "Пожалуйста, укажите тикер или адрес токена для удаления.\n"
                "Например: `/delete KVK`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Получаем тикер или адрес токена из аргументов
        token_query = context.args[0].strip()
        
        # Удаляем токен
        result = remove_specific_token(token_storage, token_query)
        
        if result:
            # Получаем информацию об удаленном токене
            ticker = token_query
            if 'data' in result and 'token_info' in result['data'] and 'ticker' in result['data']['token_info']:
                ticker = result['data']['token_info']['ticker']
            
            await update.message.reply_text(
                f"✅ Токен *{ticker}* успешно удален из списка отслеживаемых.",
                parse_mode=ParseMode.MARKDOWN
            )
            
            logger.info(f"Токен {ticker} (запрос: {result['query']}) удален пользователем {update.effective_user.id}")
        else:
            await update.message.reply_text(
                f"❌ Токен *{token_query}* не найден в списке отслеживаемых.",
                parse_mode=ParseMode.MARKDOWN
            )
            
            logger.warning(f"Попытка удаления несуществующего токена {token_query} пользователем {update.effective_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка при удалении токена: {e}")
        await update.message.reply_text(
            "Произошла ошибка при обработке запроса на удаление. Пожалуйста, попробуйте позже."
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает входящие сообщения."""
    if not update.message:
        return
    
    # Проверяем, есть ли текст в сообщении
    if update.message.text:
        query = update.message.text.strip()
        
        # Извлекаем адрес токена из сообщения, если это пересланное сообщение
        token_address = await extract_token_address_from_message(query)
        
        # Если нашли адрес, используем его вместо исходного запроса
        if token_address:
            query = token_address
            logger.info(f"Найден адрес токена в сообщении. Используем его: {query}")
    
        # Отправляем сообщение о поиске
        logger.info(f"Получено сообщение: {query}")
        try:
            msg = await update.message.reply_text(f"Ищу информацию о токене: {query}...")
            logger.info(f"Отправлено сообщение о поиске")
            
            # Получаем информацию о токене
            result = await get_token_info(query, update.message.chat_id, None, context)
            logger.info(f"Получен результат get_token_info: {'успешно' if result else 'ошибка или пустой результат'}")
            
            # Удаляем сообщение о поиске
            try:
                await msg.delete()
                logger.info(f"Сообщение о поиске удалено")
            except Exception as e:
                logger.error(f"Не удалось удалить сообщение о поиске: {e}")
                
            # Проверяем, нужно ли выполнить автоматическую проверку всех токенов
            if token_storage.check_auto_update_needed():
                logger.info("Запуск автоматической проверки Market Cap всех токенов")
                context.application.create_task(check_all_market_caps(context))
                
            # Очищаем устаревшие токены
            expired_tokens = token_storage.clean_expired_tokens()
            if expired_tokens:
                logger.info(f"Удалено {len(expired_tokens)} устаревших токенов")
                
        except Exception as e:
            logger.error(f"Критическая ошибка при обработке сообщения: {e}")
            # Пытаемся отправить сообщение об ошибке пользователю
            try:
                await update.message.reply_text("Произошла ошибка при обработке запроса. Пожалуйста, попробуйте позже.")
            except:
                logger.error("Не удалось отправить сообщение об ошибке пользователю")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает ошибки, возникающие при обработке обновлений."""
    logger.error(f"Произошла ошибка: {context.error}")

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
        
        # Обрабатываем разные типы callback
        if data.startswith("refresh:"):
            await handle_refresh_token(update, context)
        elif data == "clear_confirm":
            await handle_clear_confirm(update, context)
        elif data == "clear_cancel":
            await handle_clear_cancel(update, context)
        else:
            await query.answer("Неизвестный тип запроса")
            logger.warning(f"Неизвестный тип callback запроса: {data}")
            
    except Exception as e:
        logger.error(f"Ошибка при обработке callback запроса: {e}")
        try:
            await query.answer("Произошла ошибка. Пожалуйста, попробуйте позже.")
        except:
            pass

async def handle_refresh_token(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает запрос на обновление токена."""
    query = update.callback_query
    data = query.data
    token_query = data.split(':', 1)[1]
    
    logger.info(f"Получен запрос на обновление для токена {token_query}")
    
    # Проверяем, не слишком ли часто обновляем
    current_time = time.time()
    stored_data = token_storage.get_token_data(token_query)
    
    if stored_data:
        last_update_time = stored_data.get('last_update_time')
        if current_time - last_update_time < 5:  # Минимум 5 секунд между обновлениями
            await query.answer("Пожалуйста, подождите несколько секунд между обновлениями")
            logger.info(f"Обновление для токена {token_query} отклонено: слишком частые запросы")
            return
    else:
        # Если данных о токене нет, уведомляем и возвращаемся
        await query.answer("Информация о токене недоступна. Попробуйте заново отправить запрос.")
        logger.warning(f"Не найдены данные о токене {token_query} для обновления")
        return
    
    # Уведомляем пользователя о начале обновления
    await query.answer("Обновляю информацию...")
    logger.info(f"Начато обновление для токена {token_query}")
    
    # Получаем информацию о токене и обновляем сообщение
    result = await get_token_info(
        token_query, 
        query.message.chat_id, 
        query.message.message_id, 
        context
    )
    
    # Обновляем время последнего обновления
    if stored_data and result:
        token_storage.update_token_field(token_query, 'last_update_time', current_time)
        logger.info(f"Обновление для токена {token_query} успешно выполнено")
    else:
        logger.warning(f"Обновление для токена {token_query} не удалось")
        
    # Проверяем, нужно ли выполнить автоматическую проверку всех токенов
    if token_storage.check_auto_update_needed():
        logger.info("Запуск автоматической проверки Market Cap всех токенов")
        context.application.create_task(check_all_market_caps(context))

async def handle_clear_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает подтверждение очистки всех токенов."""
    query = update.callback_query
    
    # Получаем число токенов перед очисткой
    tokens_count = len(token_storage.get_all_tokens())
    
    # Очищаем все токены
    token_storage.clear_all_tokens()
    
    # Обновляем сообщение
    await query.edit_message_text(
        f"✅ *Успешно очищено {tokens_count} токенов.*\n\n"
        "Все данные удалены.",
        parse_mode=ParseMode.MARKDOWN
    )
    
    await query.answer("Токены успешно очищены")
    logger.info(f"Очищены все данные о токенах ({tokens_count} шт.)")

async def handle_clear_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает отмену очистки всех токенов."""
    query = update.callback_query
    
    # Обновляем сообщение
    await query.edit_message_text(
        "❌ Операция очистки отменена.\n\n"
        "Все данные о токенах сохранены.",
        parse_mode=ParseMode.MARKDOWN
    )
    
    await query.answer("Операция отменена")
    logger.info("Очистка токенов отменена пользователем")

async def setup_bot_commands(application):
    """Устанавливает список команд бота с описаниями."""
    commands = [
        BotCommand("start", "запустить бота"),
        BotCommand("stop", "остановить бота"),
        BotCommand("help", "показать справку"),
        BotCommand("list", "показать список отслеживаемых токенов"),
        BotCommand("clear", "очистить все данные о токенах"),
        BotCommand("delete", "удалить токен из списка")
    ]
    
    await application.bot.set_my_commands(commands)
    logger.info("Команды бота успешно настроены")

def main() -> None:
    """Запускает бота."""
    try:
        # Создаем приложение и передаем ему токен телеграм бота
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # Регистрируем обработчики команд
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("stop", stop))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("list", list_tokens))
        application.add_handler(CommandHandler("clear", clear_tokens))
        application.add_handler(CommandHandler("delete", delete_token_command))
        
        # Регистрируем обработчик для обычных сообщений
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        # Регистрируем обработчик для инлайн-кнопок
        application.add_handler(CallbackQueryHandler(handle_callback))
        
        # Регистрируем обработчик ошибок
        application.add_error_handler(error_handler)
        
        # Устанавливаем команды меню напрямую
        import requests
        setup_commands_direct(TELEGRAM_TOKEN)
        
        # Запускаем бота
        logger.info("Бот запущен и готов к работе")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске бота: {e}")

def setup_commands_direct(token):
    """Устанавливает команды бота напрямую через HTTP API."""
    try:
        import requests
        import json
        
        commands = [
            {"command": "start", "description": "запустить бота"},
            {"command": "stop", "description": "остановить бота"},
            {"command": "help", "description": "показать справку"},
            {"command": "list", "description": "показать список отслеживаемых токенов"},
            {"command": "clear", "description": "очистить все данные о токенах"},
            {"command": "delete", "description": "удалить токен из списка"}
        ]
        
        url = f"https://api.telegram.org/bot{token}/setMyCommands"
        response = requests.post(url, json={"commands": commands})
        
        if response.status_code == 200 and response.json().get("ok"):
            logger.info("Команды бота успешно настроены")
        else:
            logger.error(f"Ошибка при настройке команд бота: {response.text}")
    except Exception as e:
        logger.error(f"Ошибка при настройке команд бота: {e}")

if __name__ == "__main__":
    main()