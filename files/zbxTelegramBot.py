#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Zabbix Telegram Bot Callback Handler
Обработчик колбэков для интерактивных кнопок в уведомлениях Zabbix
"""
import asyncio
import logging
import sys
import ssl
from datetime import datetime

import warnings
warnings.filterwarnings("ignore", message=".*model_custom_emoji_id.*")

# ГЛОБАЛЬНОЕ ОТКЛЮЧЕНИЕ ПРОВЕРКИ SSL (для самоподписанных сертификатов)
ssl._create_default_https_context = ssl._create_unverified_context

# Импорт конфигурации
from zbxTelegram_config import *

# Aiogram
from aiogram import Bot, Dispatcher
from aiogram.types import CallbackQuery
from aiogram.filters import Filter
from aiogram.client.session.aiohttp import AiohttpSession

# Aiozabbix
from aiozabbix import ZabbixAPI
from aiozabbix.exceptions import ZabbixAPIException

# aiohttp для прокси
import aiohttp

# Логирование
log_format = logging.Formatter(
    '[%(asctime)s] - PID:%(process)s - %(funcName)s() - %(filename)s:%(lineno)d - %(levelname)s: %(message)s'
)
logger = logging.getLogger('zbxTelegramBot')
logger.setLevel(logging.DEBUG if config_debug_mode else logging.INFO)

stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setFormatter(log_format)
logger.addHandler(stdout_handler)

try:
    file_handler = logging.FileHandler(filename=config_log_file, mode='a')
    file_handler.setFormatter(log_format)
    logger.addHandler(file_handler)
except PermissionError as e:
    logger.error(f"Cannot write to log file {config_log_file}: {e}")


class CallbackFilter(Filter):
    """Фильтр для колбэков: <действие>:<eventid>"""
    def __init__(self, action: str):
        self.action = action

    async def __call__(self, callback: CallbackQuery) -> bool | dict:
        if not callback.data:  # ИСПРАВЛЕНО: .data вместо .
            return False
        parts = callback.data.split(':')
        if len(parts) >= 2 and parts[0] == self.action:
            return {'eventid': parts[1], 'extra': parts[2:] if len(parts) > 2 else []}
        return False
    

async def init_zabbix():
    """Инициализация Zabbix API без кастомных коннекторов"""
    # Простая сессия без прокси для Zabbix (прокси настраивается на уровне ОС/окружения)
    session = aiohttp.ClientSession()
    zapi = ZabbixAPI(zabbix_api_url, client_session=session)
    
    try:
        await zapi.login(zabbix_api_login, password=zabbix_api_pass)
        logger.info(f"Successfully authenticated to Zabbix API at {zabbix_api_url}")
        return zapi, session
    except Exception as e:
        logger.error(f"Failed to authenticate to Zabbix API: {e}", exc_info=True)
        await session.close()
        return None, None

async def handle_acknowledge(callback: CallbackQuery, eventid: str, zapi):
    """Подтверждение события БЕЗ закрытия (action=6 = подтверждение + сообщение)"""
    try:
        await callback.answer()
        
        # Получаем событие (числовой формат!)
        events = await zapi.event.get(
            eventids=[int(eventid)],
            output=["eventid", "value", "acknowledged", "r_eventid"],
            selectHosts=["name"]
        )
        
        if not events:
            await callback.message.answer("❌ Событие не найдено")
            logger.warning(f"Event {eventid} not found")
            return
        
        event = events[0]
        host_name = event.get('hosts', [{}])[0].get('name', 'N/A') if event.get('hosts') else 'N/A'
        
        # Проверка 1: событие уже восстановлено (есть событие восстановления)
        if event.get('r_eventid') and event['r_eventid'] != '0':
            await callback.message.answer(f"ℹ️ Проблема уже восстановлена\nХост: {host_name}")
            logger.info(f"Event {eventid} already resolved (r_eventid={event['r_eventid']})")
            return
        
        # Проверка 2: событие закрыто (value=0)
        if event['value'] == '0':
            await callback.message.answer(f"ℹ️ Событие уже восстановлено\nХост: {host_name}")
            logger.info(f"Event {eventid} value=0")
            return
        
        # Проверка 3: уже подтверждено
        if event.get('acknowledged') == '1':
            await callback.message.answer(f"ℹ️ Событие уже подтверждено ранее\nХост: {host_name}")
            logger.info(f"Event {eventid} already acknowledged")
            return
        
        # === ПОДТВЕРЖДЕНИЕ БЕЗ ЗАКРЫТИЯ (action=6) ===
        try:
            # action=6 = 2 (подтверждение) + 4 (сообщение)
            result = await zapi.event.acknowledge(
                eventids=[int(eventid)],
                action=6,
                message=f"Acknowledged via Telegram by {callback.from_user.full_name} (@{callback.from_user.username or 'N/A'})"
            )
            
            # === БЕЗОПАСНОЕ ОБНОВЛЕНИЕ СООБЩЕНИЯ (для текста, изображений и медиа) ===
            ack_text = f"\n\n✅ Подтверждено: {callback.from_user.full_name}\nХост: {host_name}"
            
            # Случай 1: текстовое сообщение
            if callback.message.text:
                new_text = (callback.message.text + ack_text)[:4096]  # Ограничение Telegram на 4096 символов
                await callback.message.edit_text(
                    new_text,
                    reply_markup=None,
                    parse_mode="HTML"
                )
            
            # Случай 2: медиа-сообщение (изображение/видео) с подписью
            elif callback.message.caption:
                new_caption = (callback.message.caption + ack_text)[:1024]  # Ограничение на подпись — 1024 символа
                await callback.message.edit_caption(
                    caption=new_caption,
                    reply_markup=None,
                    parse_mode="HTML"
                )
            
            # Случай 3: сообщение без текста и подписи (крайне редко)
            else:
                await callback.message.answer(
                    f"✅ Событие #{eventid} подтверждено пользователем {callback.from_user.full_name}\nХост: {host_name}",
                    reply_markup=None
                )
            
            logger.info(f"Event {eventid} acknowledged (action=6) by user {callback.from_user.id}")
            
        except ZabbixAPIException as e:
            error_code = e.args[1] if len(e.args) > 1 else None
            error_msg = e.args[0] if e.args else "Unknown error"
            
            # Проверка после ошибки (гонка условий)
            post_check = await zapi.event.get(
                eventids=[int(eventid)],
                output=["acknowledged", "r_eventid", "value"]
            )
            
            if post_check:
                post_event = post_check[0]
                if post_event.get('acknowledged') == '1':
                    await callback.message.answer(f"✅ Событие уже подтверждено\nХост: {host_name}")
                    logger.info(f"Event {eventid} already acknowledged (race condition)")
                elif post_event.get('r_eventid') and post_event['r_eventid'] != '0':
                    await callback.message.answer(f"ℹ️ Проблема восстановилась до подтверждения\nХост: {host_name}")
                    logger.info(f"Event {eventid} resolved during acknowledge")
                elif error_code == -32500 and 'manual closing' in str(error_msg).lower():
                    await callback.message.answer(
                        f"⚠️ Ошибка: попытка закрытия проблемы запрещена триггером.\n"
                        f"Исправлено: теперь используется действие 'Подтвердить' (без закрытия).\n"
                        f"Хост: {host_name}"
                    )
                    logger.error(f"Event {eventid} failed with action=1 — must use action=6")
                else:
                    await callback.message.answer(f"❌ Ошибка Zabbix API ({error_code}): {str(error_msg)[:70]}")
                    logger.error(f"Zabbix API error for event {eventid}: {e}", exc_info=True)
            else:
                await callback.message.answer("❌ Событие удалено из системы")
                logger.warning(f"Event {eventid} disappeared")
    
    except ValueError as e:
        await callback.message.answer(f"❌ Неверный формат ID события: {eventid}")
        logger.error(f"Invalid eventid format '{eventid}': {e}")
    except Exception as e:
        await callback.message.answer(f"❌ Внутренняя ошибка: {str(e)[:80]}")
        logger.error(f"Unexpected error for event {eventid}: {e}", exc_info=True)



async def handle_messages(callback: CallbackQuery, eventid: str, zapi):
    """Показать сообщения/комментарии к событию с проверкой существования"""
    try:
        await callback.answer()
        
        # Проверка существования события
        events = await zapi.event.get(
            eventids=[eventid],
            output=["eventid"],
            select_acknowledges="extend"
        )
        
        if not events:
            await callback.message.answer("❌ Событие не найдено")
            logger.warning(f"Event {eventid} not found for messages request")
            return
        
        event = events[0]
        acks = event.get('acknowledges', [])
        
        if not acks:
            text = "📝 Нет комментариев к событию"
        else:
            comments = []
            for ack in sorted(acks, key=lambda x: int(x['clock']), reverse=True)[:5]:
                dt = datetime.fromtimestamp(int(ack['clock']))
                user = ack.get('alias', ack.get('name', 'Unknown'))
                msg = ack.get('message', '').strip() or '(без комментария)'
                comments.append(f"▫️ {dt.strftime('%Y-%m-%d %H:%M')} — {user}:\n   {msg}")
            
            text = "📝 Комментарии к событию:\n" + "\n\n".join(comments)
        
        await callback.message.answer(text, disable_notification=True)
        logger.info(f"Messages shown for event {eventid}")
        
    except ZabbixAPIException as e:
        error_code = e.args[1] if len(e.args) > 1 else None
        error_msg = e.args[0] if e.args else "Unknown error"
        await callback.message.answer(f"❌ Ошибка Zabbix API ({error_code}): {str(error_msg)[:80]}")
        logger.error(f"Zabbix API error for event {eventid} messages: {e}", exc_info=True)
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка получения комментариев: {str(e)[:80]}")
        logger.error(f"Error getting messages for event {eventid}: {e}", exc_info=True)



async def handle_history(callback: CallbackQuery, eventid: str, zapi):
    """Показать историю события с ТЕКУЩИМ статусом проблемы"""
    try:
        await callback.answer()
        
        # Получаем событие с данными о восстановлении (числовой формат!)
        events = await zapi.event.get(
            eventids=[int(eventid)],  # ← ЧИСЛО
            output=["eventid", "clock", "value", "r_eventid", "objectid"],
            selectHosts=["hostid", "name"],
            selectRelatedObject=["description", "expression"]
        )
        
        if not events:
            await callback.message.answer("❌ Событие не найдено")
            logger.warning(f"Event {eventid} not found for history request")
            return
        
        event = events[0]
        host_name = event.get('hosts', [{}])[0].get('name', 'N/A') if event.get('hosts') else 'N/A'
        trigger_name = event.get('relatedObject', {}).get('description', 'N/A')
        event_time = datetime.fromtimestamp(int(event['clock'])).strftime('%Y-%m-%d %H:%M:%S')
        
        # Определяем ТЕКУЩИЙ статус проблемы
        current_status = "🔴 АКТИВНА"
        status_details = ""
        restore_time_str = ""
        
        r_eventid = event.get('r_eventid')
        if r_eventid and r_eventid != '0':
            # Проблема восстановлена — получаем время восстановления
            restore_events = await zapi.event.get(
                eventids=[int(r_eventid)],
                output=["clock", "value"]
            )
            if restore_events:
                restore_event = restore_events[0]
                restore_time = datetime.fromtimestamp(int(restore_event['clock'])).strftime('%Y-%m-%d %H:%M:%S')
                restore_time_str = restore_time
                current_status = "🟢 ВОССТАНОВЛЕНА"
                status_details = f"\nВремя восстановления: {restore_time}"
            else:
                current_status = "🟢 ВОССТАНОВЛЕНА (время неизвестно)"
        else:
            # Проверяем через problem.get для уверенности
            problems = await zapi.problem.get(
                eventids=[int(eventid)],
                output=["eventid"]
            )
            if not problems:
                current_status = "🟢 ВОССТАНОВЛЕНА (активная проблема не найдена)"
        
        # Формируем сообщение
        text = (
            f"📈 Событие #{eventid}\n"
            f"Текущий статус: {current_status}\n"
            f"Время события: {event_time}{status_details}\n"
            f"Хост: {host_name}\n"
            f"Триггер: {trigger_name}"
        )
        
        await callback.message.answer(text, disable_notification=True)
        logger.info(f"History shown for event {eventid} (current status: {current_status})")
        
    except ZabbixAPIException as e:
        error_code = e.args[1] if len(e.args) > 1 else None
        error_msg = e.args[0] if e.args else "Unknown error"
        await callback.message.answer(f"❌ Ошибка Zabbix API ({error_code}): {str(error_msg)[:80]}")
        logger.error(f"Zabbix API error for event {eventid} history: {e}", exc_info=True)
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка получения истории: {str(e)[:80]}")
        logger.error(f"Error getting history for event {eventid}: {e}", exc_info=True)



async def handle_last_value(callback: CallbackQuery, eventid: str, zapi):
    """Показать последнее значение элемента данных с проверкой существования"""
    try:
        await callback.answer()
        
        # Проверка существования события
        events = await zapi.event.get(
            eventids=[eventid],
            output=["eventid", "objectid"]
        )
        
        if not events:
            await callback.message.answer("❌ Событие не найдено")
            logger.warning(f"Event {eventid} not found for last value request")
            return
        
        triggerid = events[0]['objectid']
        
        # Получаем элементы данных
        items = await zapi.item.get(
            triggerids=[triggerid],
            output=["name", "lastvalue", "lastclock", "units"],
            sortfield="name",
            limit=5
        )
        
        if not items:
            await callback.message.answer("ℹ️ Нет данных для отображения")
            return
        
        lines = ["⏱ Последние значения:"]
        for item in items:
            dt = datetime.fromtimestamp(int(item['lastclock'])) if item.get('lastclock') else None
            value = item.get('lastvalue', 'N/A')
            units = f" {item['units']}" if item.get('units') and item['units'] != 'unixtime' else ""
            time_str = f" ({dt.strftime('%H:%M:%S')})" if dt else ""
            lines.append(f"▫️ {item['name']}: {value}{units}{time_str}")
        
        await callback.message.answer("\n".join(lines), disable_notification=True)
        logger.info(f"Last values shown for event {eventid}")
        
    except ZabbixAPIException as e:
        error_code = e.args[1] if len(e.args) > 1 else None
        error_msg = e.args[0] if e.args else "Unknown error"
        await callback.message.answer(f"❌ Ошибка Zabbix API ({error_code}): {str(error_msg)[:80]}")
        logger.error(f"Zabbix API error for event {eventid} last value: {e}", exc_info=True)
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка получения значений: {str(e)[:80]}")
        logger.error(f"Error getting last values for event {eventid}: {e}", exc_info=True)



async def handle_graphs(callback: CallbackQuery, eventid: str, extra: list, zapi):
    """Показать график (ссылка на график в Zabbix)"""
    try:
        await callback.answer()
        
        # Проверка существования события
        events = await zapi.event.get(
            eventids=[eventid],
            output=["eventid"]
        )
        
        if not events:
            await callback.message.answer("❌ Событие не найдено")
            logger.warning(f"Event {eventid} not found for graph request")
            return
        
        itemid = extra[0] if extra else None
        
        if itemid:
            # Формат URL: https://zabbix.tspd.local/history.php?action=showgraph&itemids%5B%5D=123456
            graph_url = f"{zabbix_api_url.rstrip('/')}/history.php?action=showgraph&itemids%5B%5D={itemid}"
            text = f"📊 График элемента данных:\n{graph_url}"
        else:
            # Ссылка на событие в интерфейсе Zabbix
            event_url = zabbix_event_link.format(
                zabbix_server=zabbix_api_url.rstrip('/'),
                eventid=eventid,
                triggerid='0'
            )
            text = f"📊 Открыть событие в Zabbix:\n{event_url}"
        
        await callback.message.answer(text, disable_web_page_preview=False)
        logger.info(f"Graph link sent for event {eventid}, itemid={itemid}")
        
    except ZabbixAPIException as e:
        error_code = e.args[1] if len(e.args) > 1 else None
        error_msg = e.args[0] if e.args else "Unknown error"
        await callback.message.answer(f"❌ Ошибка Zabbix API ({error_code}): {str(error_msg)[:80]}")
        logger.error(f"Zabbix API error for event {eventid} graph: {e}", exc_info=True)
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка получения графика: {str(e)[:80]}")
        logger.error(f"Error getting graph for event {eventid}: {e}", exc_info=True)


async def handle_unknown(callback: CallbackQuery):
    """Обработчик неизвестных колбэков"""
    await callback.answer("❓ Неизвестная команда", show_alert=True)
    logger.warning(f"Unknown callback received: {callback.data}")


async def main():
    logger.info("Starting Zabbix Telegram Bot Callback Handler...")
    
    # Инициализация Zabbix
    zapi, zabbix_session = await init_zabbix()
    if not zapi:
        logger.critical("Cannot start bot without Zabbix API connection")
        return 1
    
    # Настройка прокси для Telegram (простой вариант)
    proxy_url = None
    if tg_proxy and tg_proxy_server:
        if isinstance(tg_proxy_server, dict):
            proxy_url = next(iter(tg_proxy_server.values()))
        else:
            proxy_url = tg_proxy_server
        logger.info(f"Using proxy for Telegram API: {proxy_url}")
    
    # Инициализация бота БЕЗ кастомных коннекторов
    bot_session = AiohttpSession(proxy=proxy_url) if proxy_url else AiohttpSession()
    bot = Bot(token=tg_token, session=bot_session)
    
    # Проверка подключения
    try:
        me = await bot.get_me()
        logger.info(f"Bot @{me.username} (id={me.id}) started successfully")
    except Exception as e:
        logger.critical(f"Cannot connect to Telegram API: {e}", exc_info=True)
        await zabbix_session.close()
        await bot_session.close()
        return 1
    
    # Регистрация обработчиков
    dp = Dispatcher()
    
    @dp.callback_query(CallbackFilter(action="a"))
    async def cb_ack(callback: CallbackQuery, eventid: str):
        await handle_acknowledge(callback, eventid, zapi)
    
    @dp.callback_query(CallbackFilter(action="m"))
    async def cb_msg(callback: CallbackQuery, eventid: str):
        await handle_messages(callback, eventid, zapi)
    
    @dp.callback_query(CallbackFilter(action="h"))
    async def cb_hist(callback: CallbackQuery, eventid: str):
        await handle_history(callback, eventid, zapi)
    
    @dp.callback_query(CallbackFilter(action="l"))
    async def cb_last(callback: CallbackQuery, eventid: str):
        await handle_last_value(callback, eventid, zapi)
    
    @dp.callback_query(CallbackFilter(action="g"))
    async def cb_graph(callback: CallbackQuery, eventid: str, extra: list):
        await handle_graphs(callback, eventid, extra, zapi)
    
    @dp.callback_query()
    async def cb_unknown(callback: CallbackQuery):
        await handle_unknown(callback)
    
    # Запуск
    logger.info("Bot is ready to receive callbacks...")
    try:
        await dp.start_polling(bot, handle_signals=True)
    finally:
        await bot_session.close()
        await zabbix_session.close()
        logger.info("Bot stopped gracefully")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.critical(f"Unhandled exception: {e}", exc_info=True)
        