#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Zabbix Telegram Alert Script (aiogram 3.x)
Полностью заменяет pyTelegramBotAPI на aiogram
"""
import asyncio
import sys
import os
import re
import io
import json
import logging
import argparse
import ssl  # ← КРИТИЧЕСКИ ВАЖНЫЙ ИМПОРТ
from argparse import RawTextHelpFormatter
from datetime import datetime
from errno import ENOENT
import html

import warnings
warnings.filterwarnings("ignore", message=".*model_custom_emoji_id.*")

# ГЛОБАЛЬНОЕ ОТКЛЮЧЕНИЕ ПРОВЕРКИ SSL (для самоподписанных сертификатов)
ssl._create_default_https_context = ssl._create_unverified_context

# Aiogram компоненты
from aiogram import Bot
from aiogram.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    InputMediaPhoto,
    BufferedInputFile
)

from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramAPIError

# XML обработка
import xmltodict

# PIL для водяных знаков
from PIL import Image, ImageDraw, ImageFont

# Конфигурация
from zbxTelegram_config import *

# HTTP для получения кук и графиков
import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context
from urllib3.exceptions import InsecureRequestWarning

urllib3.disable_warnings(InsecureRequestWarning)

# SSL адаптер для requests (для get_cookie и get_chart_png)
class SSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        context = create_urllib3_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        kwargs['ssl_context'] = context
        return super(SSLAdapter, self).init_poolmanager(*args, **kwargs)

session = requests.Session()
session.mount('https://', SSLAdapter())
session.mount('http://', SSLAdapter())

# Логирование
class System:
    def __init__(self, debug=False):
        self.log_level = logging.DEBUG if debug else logging.INFO
        log_format = logging.Formatter(
            '[%(asctime)s] - PID:%(process)s - %(funcName)s() - %(filename)s:%(lineno)d - %(levelname)s: %(message)s'
        )
        self.log = logging.getLogger()
        self.log.setLevel(self.log_level)
        
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setLevel(self.log_level)
        stdout_handler.setFormatter(log_format)
        
        try:
            file_handler = logging.FileHandler(filename=config_log_file, mode='a')
            file_handler.setLevel(self.log_level)
            file_handler.setFormatter(log_format)
            self.log.addHandler(file_handler)
        except PermissionError as e:
            print(f"Cannot write to log file {config_log_file}: {e}", file=sys.stderr)
        
        self.log.addHandler(stdout_handler)

class ArgParsing:
    def create_parser(self):
        parser = argparse.ArgumentParser(
            prog='znt',
            description='Скрипт для отправки Zabbix нотификаций в Telegram',
            epilog='(c) Dmitry Sokolov 2019 @ https://github.com/xxsokolov/',
            add_help=False,
            formatter_class=RawTextHelpFormatter
        )
        parser.add_argument('username', nargs='?', help='Set username Telegram')
        parser.add_argument('subject', nargs='?', help='Set subject')
        parser.add_argument('messages', nargs='?', help='Set message')
        parser.add_argument('token', nargs='?', help='Set token', default=False)
        parser.add_argument('--debug', type=str, nargs='?', const=True, default=False, help='Debug mode')
        return parser

class FailSafeDict(dict):
    def __missing__(self, key):
        return '{{key not found: {}}}'.format(key)

# Глобальный логгер
loggings = None

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def xml_parsing(data):
    try:
        data = dict(xmltodict.parse(data, process_namespaces=True)['root'])
        message = data['body']['messages']
        return dict(
            title=data['settings']['title'],
            message=message,
            eventtags=data['settings']['eventtags'],
            settings_graphs_bool=eval(data['settings']['graphs'].capitalize()),
            settings_graphlinks_bool=eval(data['settings']['graphlinks'].capitalize()),
            settings_triggerlinks_bool=eval(data['settings']['triggerlinks'].capitalize()),
            settings_hostlinks_bool=eval(data['settings']['hostlinks'].capitalize()),
            settings_acklinks_bool=eval(data['settings']['acklinks'].capitalize()),
            settings_eventlinks_bool=eval(data['settings']['eventlinks'].capitalize()),
            settings_eventtag_bool=eval(data['settings']['eventtag'].capitalize()),
            settings_eventidtag_bool=eval(data['settings']['eventidtag'].capitalize()),
            settings_itemidtag_bool=eval(data['settings']['itemidtag'].capitalize()),
            settings_triggeridtag_bool=eval(data['settings']['triggeridtag'].capitalize()),
            settings_actionidtag_bool=eval(data['settings']['actionidtag'].capitalize()),
            settings_hostidtag_bool=eval(data['settings']['hostidtag'].capitalize()),
            settings_zntsettingstag_bool=eval(data['settings']['zntsettingstag'].capitalize()),
            settings_zntmentions_bool=eval(data['settings']['zntmentions'].capitalize()),
            settings_keyboard_bool=eval(data['settings']['keyboard'].capitalize()),
            graphs_period=data['settings']['graphs_period'],
            host=data['settings']['host'],
            itemid=data['settings']['itemid'],
            triggerid=data['settings']['triggerid'],
            triggerurl=data['settings']['triggerurl'],
            eventid=data['settings']['eventid'],
            actionid=data['settings']['actionid'],
            hostid=data['settings']['hostid']
        )
    except Exception as err:
        if loggings:
            loggings.error(f"Exception occurred: No XML in zabbix actions or it's not valid. Error: {err}", exc_info=config_exc_info)
        else:
            print(f"XML parsing error: {err}", file=sys.stderr)
        sys.exit(1)

def watermark_text(img):
    try:
        img = io.BytesIO(img)
        img = Image.open(img)
        if img.height < watermark_minimal_height:
            if loggings:
                loggings.info(f"Cannot set watermark text, img height {img.height} (min. {watermark_minimal_height})")
            return False
        font = ImageFont.truetype(watermark_font, 14)
        line_height = sum(font.getmetrics())
        if hasattr(font, 'getbbox'):
            text_width = font.getbbox(watermark_label)[2]
        else:
            text_width = font.getsize(watermark_label)[0]
        fontimage = Image.new('L', (text_width, line_height))
        ImageDraw.Draw(fontimage).text((0, 0), watermark_label, fill=watermark_fill, font=font)
        fontimage = fontimage.rotate(watermark_rotate, resample=Image.BICUBIC, expand=True)
        img_size = img.crop().size
        size = (img_size[0] - fontimage.size[0] - 5, img_size[1] - fontimage.size[1] - 10)
        img.paste(watermark_text_color, box=size, mask=fontimage)
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format=img.format)
        return img_byte_arr.getvalue()
    except Exception as e:
        if loggings:
            loggings.warning(f"Watermark failed: {e}")
        return img  # ← Возвращаем оригинальное изображение при ошибке

def get_cookie():
    data_api = {"name": zabbix_api_login, "password": zabbix_api_pass, "enter": "Sign in"}
    req_cookie = session.post(zabbix_api_url, data=data_api, verify=False)
    cookie = req_cookie.cookies
    req_cookie.close()
    if not any(_ in cookie for _ in ['zbx_session', 'zbx_sessionid']):
        if loggings:
            loggings.error(f'User authorization failed: Login name or password is incorrect. ({zabbix_api_url})')
        return False
    return cookie

def get_chart_png(itemid, graff_name, period=None):
    try:
        cookies = get_cookie()
        if not cookies:
            return None
        
        response = session.get(
            zabbix_graph_chart.format(
                name=graff_name,
                itemid=itemid,
                zabbix_server=zabbix_api_url.rstrip('/'),
                range_time=period or zabbix_graph_period_default
            ),
            cookies=cookies,
            verify=False,
            timeout=10
        )
        response.raise_for_status()
        
        img_data = response.content
        if watermark and img_data:  # ← ИСПРАВЛЕНО: было `img_`
            wmt = watermark_text(img_data)
            if wmt:
                img_data = wmt
        
        return dict(img=img_data, url=response.url)
    except Exception as err:
        if loggings:
            loggings.error(f"Exception occurred getting chart: {err}", exc_info=config_exc_info)
        return None

def create_tags_list(_bool=False, tag=None, _type=None, zntsettingstag=False):
    tags_list = []
    settings_list = []
    try:
        if _bool and tag and re.search(r'\w', tag):
            for tags in tag.split(', '):
                if not tags:
                    continue
                if not zntsettingstag:
                    if ':' in tags:
                        tag_key, value = tags.split(':', 1)
                        if tag_key != trigger_settings_tag and tag_key != trigger_info_mentions_tag:
                            tag_clean = re.sub(r"\W+", "_", tag_key)
                            value_clean = re.sub(r"\W+", "_", value)
                            tags_list.append(f'#{_type}{tag_clean}_{value_clean}' if _type else f'#{tag_clean}_{value_clean}')
                    else:
                        for tg_s in tags.split():
                            tag_clean = re.sub(r"\W+", "_", tg_s)
                            tags_list.append(f'#{_type}{tag_clean}' if _type else f'#{tag_clean}')
                else:
                    if ':' in tags:
                        tag_key, value = tags.split(':', 1)
                        if tag_key == trigger_settings_tag:
                            tag_clean = re.sub(r"\W+", "_", tag_key)
                            value_clean = re.sub(r"\W+", "_", value)
                            tags_list.append(f'#{_type}{tag_clean}_{value_clean}' if _type else f'#{tag_clean}_{value_clean}')
                            settings_list.append(value)
            return body_messages_tags_delimiter.join(tags_list) if not zntsettingstag else {
                'tags': body_messages_tags_delimiter.join(tags_list),
                trigger_settings_tag: settings_list
            }
        return body_messages_tags_no if not zntsettingstag else {'tags': body_messages_tags_no, trigger_settings_tag: []}
    except Exception as e:
        if loggings:
            loggings.warning(f"Tags creation failed: {e}")
        return body_messages_tags_no if not zntsettingstag else {'tags': body_messages_tags_no, trigger_settings_tag: []}

def create_mentions_list(_bool=False, mentions=None):
    mentions_list = []
    try:
        if _bool and mentions:
            for tags in mentions.split(', '):
                if ':' in tags:
                    tag_key, value = tags.split(':', 1)
                    if tag_key == trigger_info_mentions_tag:
                        for username in value.split():
                            mentions_list.append(username)
        return mentions_list
    except Exception as e:
        if loggings:
            loggings.warning(f"Mentions creation failed: {e}")
        return []

def create_links_list(_bool=None, url=None, _type=None, url_list=None):
    try:
        if _bool and url and re.search(r'\w', url):
            return body_messages_url_template.format(url=url, icon=_type)
        return body_messages_url_emoji_no_url if _bool else (url_list if url_list else False)
    except Exception as e:
        if loggings:
            loggings.warning(f"Links creation failed: {e}")
        return body_messages_url_emoji_no_url if _bool else False

def get_cache(title):
    try:
        if not os.path.exists(config_cache_file):
            raise IOError(ENOENT, 'No such file or directory', config_cache_file)
        with open(config_cache_file, 'r') as f:
            cache = json.load(f)
            return cache.get(title, {}).get('id')
    except Exception as err:
        if loggings:
            loggings.error(f"Cache read error: {err}", exc_info=config_exc_info)
        return False

def set_cache(title, send_id, sent_type, cache=None, update=None):
    try:
        try:
            with open(config_cache_file, 'r') as f:
                cache = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            cache = {}
        
        cache[title] = {
            'type': str(sent_type),
            'id': str(send_id),
            **({'old': str(update)} if update else {})
        }
        
        os.makedirs(os.path.dirname(config_cache_file), exist_ok=True)
        with open(config_cache_file, 'w') as f:
            json.dump(cache, f, sort_keys=True, ensure_ascii=False, indent=4)
        
        if loggings:
            if update:
                loggings.info(f"Updated id for {title} ({sent_type}): old '{update}' -> new '{send_id}' in cache file")
            else:
                loggings.info(f"Add new id {send_id} for {title} ({sent_type}) in cache file")
        return True
    except Exception as err:
        if loggings:
            loggings.error(f"Cache write error: {err}", exc_info=config_exc_info)
        return False


def set_period_day_hour(seconds):
    seconds = int(seconds)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, _ = divmod(seconds, 60)
    if days > 0:
        return f'{days}d {hours}h' if hours > 0 else f'{days}d'
    elif hours > 0:
        return f'{hours}h {minutes}m' if minutes > 0 else f'{hours}h'
    elif minutes > 0:
        return f'{minutes}m'
    return '0m'


def gen_markup(eventid, itemid=None):
    """Создаёт клавиатуру с компактными колбэками (≤64 байт)"""
    buttons = [
        InlineKeyboardButton(text="💬", callback_data=f"m:{eventid}"),
        InlineKeyboardButton(text="✅", callback_data=f"a:{eventid}"),
        InlineKeyboardButton(text="📈", callback_data=f"h:{eventid}"),
        InlineKeyboardButton(text="⏱", callback_data=f"l:{eventid}"),
    ]
    if itemid and re.search(r'\d+', itemid):
        clean_itemid = re.search(r'\d+', itemid).group()
        buttons.append(InlineKeyboardButton(text="📊", callback_data=f"g:{eventid}:{clean_itemid}"))
    
    # Защита от отсутствия переменной в конфигурации
    row_width = getattr(sys.modules[__name__], 'zabbix_keyboard_row_width', 5)
    rows = [buttons[i:i+row_width] for i in range(0, len(buttons), row_width)]
    
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ==================== АСИНХРОННЫЕ ФУНКЦИИ TELEGRAM ====================
async def get_send_id(bot: Bot, send_to: str) -> int:
    """Получает chat_id по имени чата/пользователя (асинхронная версия)"""
    try:
        # Прямой числовой ID
        if re.fullmatch(r'-?\d+', send_to):
            return int(send_to)
        
        # Имя пользователя (@username)
        if send_to.startswith('@'):
            send_to = send_to[1:]
        
        # Проверка кэша
        send_id = get_cache(send_to)
        if send_id:
            return int(send_id)
        
        if loggings:
            loggings.info("Telegram API: method getUpdates: started")
        
        # Получаем обновления для поиска чата
        updates = await bot.get_updates(timeout=10)
        while len(updates) >= 100:
            last_id = max(u.update_id for u in updates)
            updates = await bot.get_updates(timeout=10, offset=last_id + 1)
        
        for update in updates:
            chat = None
            if update.message:
                chat = update.message.chat
            elif update.edited_message:
                chat = update.edited_message.chat
            elif update.channel_post:
                chat = update.channel_post.chat
            
            if not chat:
                continue
            
            # Поиск по названию чата/канала
            if chat.type in ["group", "supergroup", "channel"] and chat.title == send_to:
                set_cache(send_to, chat.id, chat.type)
                await bot.get_updates(offset=-1)
                return chat.id
            
            # Поиск по имени пользователя
            if chat.type == "private" and chat.username and chat.username.lower() == send_to.lower():
                set_cache(send_to, chat.id, chat.type)
                await bot.get_updates(offset=-1)
                return chat.id
        
        raise ValueError(f'Username/group "{send_to}" not found. Add bot to group or send message to bot first.')
    
    except Exception as err:
        if loggings:
            loggings.error(f"Exception in get_send_id: {err}", exc_info=config_exc_info)
        sys.exit(1)


async def send_messages(
    bot: Bot,
    sent_to: str,
    message: str,
    media_data,
    eventid: str = None,
    itemid: str = None,
    settings_keyboard: bool = None,
    disable_notification: bool = False
):
    """Отправка сообщения в Telegram (асинхронная версия)"""
    try:
        sent_id = await get_send_id(bot, sent_to)
        if not message or not sent_to:
            if loggings:
                loggings.warning(f"Cannot send message: empty message or recipient (sent_to={sent_to})")
            return

        # Случай 1: список медиа (несколько графиков)
        if isinstance(media_data, list) and media_data:
            try:
                # Преобразуем байты в BufferedInputFile для каждого изображения
                media_group = []
                for i, media in enumerate(media_data):
                    if isinstance(media, InputMediaPhoto) and isinstance(media.media, bytes):
                        media.media = BufferedInputFile(media.media, filename=f"chart_{i}.png")
                    media_group.append(media)
                
                media_group[0].caption = message
                media_group[0].parse_mode = "HTML"
                await bot.send_media_group(
                    chat_id=sent_id,
                    media=media_group,
                    disable_notification=disable_notification
                )
                if loggings:
                    me = await bot.me()
                    loggings.info(f'Bot @{me.username}({me.id}) send media group to "{sent_to}" ({sent_id}).')
                sys.exit(0)
            except TelegramAPIError as err:
                if hasattr(err, 'migrate_to_chat_id') and getattr(err, 'migrate_to_chat_id', None):
                    if loggings:
                        loggings.warning(f"Group chat migrated to supergroup {err.migrate_to_chat_id}")
                    set_cache(sent_to, err.migrate_to_chat_id, 'supergroup', update=sent_id)
                    await send_messages(bot, sent_to, message, media_data, eventid, itemid, settings_keyboard, disable_notification)
                else:
                    raise

        # Случай 2: словарь с изображением (один график)
        elif isinstance(media_data, dict) and media_data.get('img'):
            try:
                # Преобразуем байты в BufferedInputFile
                photo_file = BufferedInputFile(media_data['img'], filename="chart.png")
                await bot.send_photo(
                    chat_id=sent_id,
                    photo=photo_file,
                    caption=message,
                    parse_mode="HTML",
                    reply_markup=gen_markup(eventid, itemid) if zabbix_keyboard and settings_keyboard else None,
                    disable_notification=disable_notification
                )
                if loggings:
                    me = await bot.me()
                    loggings.info(f'Bot @{me.username}({me.id}) send photo to "{sent_to}" ({sent_id}).')
            except TelegramAPIError as err:
                if hasattr(err, 'migrate_to_chat_id') and getattr(err, 'migrate_to_chat_id', None):
                    if loggings:
                        loggings.warning(f"Group chat migrated to supergroup {err.migrate_to_chat_id}")
                    set_cache(sent_to, err.migrate_to_chat_id, 'supergroup', update=sent_id)
                    await send_messages(bot, sent_to, message, media_data, eventid, itemid, settings_keyboard, disable_notification)
                elif "IMAGE_PROCESS_FAILED" in str(err):
                    fallback_path = f'{os.path.dirname(os.path.realpath(__file__))}/zbxTelegram_files/error_send_photo.png'
                    try:
                        with open(fallback_path, 'rb') as f:
                            fallback_img = f.read()
                        fallback_file = BufferedInputFile(fallback_img, filename="error.png")
                        await bot.send_photo(
                            chat_id=sent_id,
                            photo=fallback_file,
                            caption=message,
                            parse_mode="HTML",
                            reply_markup=gen_markup(eventid, itemid) if zabbix_keyboard and settings_keyboard else None,
                            disable_notification=disable_notification
                        )
                    except Exception as e:
                        if loggings:
                            loggings.error(f"Fallback image failed: {e}")
                        raise
                else:
                    raise

        # Случай 3: текстовое сообщение
        else:
            try:
                await bot.send_message(
                    chat_id=sent_id,
                    text=message,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                    reply_markup=gen_markup(eventid, itemid) if zabbix_keyboard and settings_keyboard else None,
                    disable_notification=disable_notification
                )
                if loggings:
                    me = await bot.me()
                    loggings.info(f'Bot @{me.username}({me.id}) send message to "{sent_to}" ({sent_id}).')
                sys.exit(0)
            except TelegramAPIError as err:
                if hasattr(err, 'migrate_to_chat_id') and getattr(err, 'migrate_to_chat_id', None):
                    if loggings:
                        loggings.warning(f"Group chat migrated to supergroup {err.migrate_to_chat_id}")
                    set_cache(sent_to, err.migrate_to_chat_id, 'supergroup', update=sent_id)
                    await send_messages(bot, sent_to, message, media_data, eventid, itemid, settings_keyboard, disable_notification)
                else:
                    raise

    except SystemExit:
        raise
    except Exception as err:
        if loggings:
            loggings.error(f"Exception in send_messages: {err}", exc_info=config_exc_info)
        sys.exit(1)


# ==================== ОСНОВНАЯ АСИНХРОННАЯ ФУНКЦИЯ ====================
async def main_async():
    global loggings
    
    # Парсинг аргументов
    args = ArgParsing().create_parser().parse_args(sys.argv[1:])
    loggings = System(config_debug_mode if not args.debug else True).log
    
    if loggings:
        loggings.info(f"Send to {args.username} action: {args.subject}")
        loggings.debug(f"sys.argv: {sys.argv[1:]}")
    
    # Настройка прокси (без кастомных коннекторов!)
    proxy_url = None
    if tg_proxy and tg_proxy_server:
        proxy_url = tg_proxy_server if isinstance(tg_proxy_server, str) else next(iter(tg_proxy_server.values()))
        if loggings:
            loggings.info(f"Using proxy for Telegram API: {proxy_url}")
    
    # Создаём сессию БЕЗ кастомного коннектора (SSL отключён глобально)
    bot_session = AiohttpSession(proxy=proxy_url) if proxy_url else AiohttpSession()
    bot = Bot(token=args.token if args.token else tg_token, session=bot_session)
    
    try:
        # Тестовый режим
        if args.subject in ['Test subject', 'test', 'Тестовая тема'] or args.messages in \
                ['This is the test message from Zabbix', 'test', 'Это тестовое сообщение от Zabbix']:
            if get_cookie():
                if loggings:
                    loggings.info(f'Connection check passed ({zabbix_api_url})')
                test_graph_file = f'{os.path.dirname(os.path.realpath(__file__))}/zbxTelegram_files/test.png'
                error_code = 0
            else:
                test_graph_file = f'{os.path.dirname(os.path.realpath(__file__))}/zbxTelegram_files/error_send_photo.png'
                error_code = 1
            
            try:
                with open(test_graph_file, 'rb') as f:
                    img_data = f.read()
            except FileNotFoundError:
                if loggings:
                    loggings.error(f"Test image not found: {test_graph_file}")
                sys.exit(1)
            
            await send_messages(
                bot=bot,
                sent_to=args.username,
                message='🚨 Test: Test message with buttons\n'
                        'Host: testhost [192.168.0.0]\n'
                        'Last value: test (10:00:00)\n'
                        'Duration: 1m\n'
                        'Description: This message is generated with test data.\n\n'
                        '#Test #eid_12345 #iid_67890',
                media_data=dict(img=img_data),
                eventid="12345",
                itemid="67890",
                settings_keyboard=True,
                disable_notification=False
            )
            sys.exit(error_code)
        
        # Основной режим: парсинг XML
        data_zabbix = xml_parsing(args.messages)
        
        # Формирование тегов
        event_tags = create_tags_list(
            _bool=data_zabbix.get('settings_eventtag_bool') and body_messages_tags_event,
            tag=data_zabbix['eventtags']
        )
        eventid_tags = create_tags_list(
            _bool=data_zabbix.get('settings_eventidtag_bool') and body_messages_tags_eventid,
            tag=data_zabbix['eventid'],
            _type=body_messages_tags_prefix_eventid
        )
        itemid_tags = create_tags_list(
            _bool=data_zabbix.get('settings_itemidtag_bool') and body_messages_tags_itemid,
            tag=' '.join([item_id for item_id in data_zabbix['itemid'].split() if re.search(r"\d+", item_id)]),
            _type=body_messages_tags_prefix_itemid
        )
        triggerid_tags = create_tags_list(
            _bool=data_zabbix.get('settings_triggeridtag_bool') and body_messages_tags_triggerid,
            tag=data_zabbix['triggerid'],
            _type=body_messages_tags_prefix_triggerid
        )
        actionid_tags = create_tags_list(
            _bool=data_zabbix.get('settings_actionidtag_bool') and body_messages_tags_actionid,
            tag=data_zabbix['actionid'],
            _type=body_messages_tags_prefix_actionid
        )
        hostid_tags = create_tags_list(
            _bool=data_zabbix.get('settings_hostidtag_bool') and body_messages_tags_hostid,
            tag=data_zabbix['hostid'],
            _type=body_messages_tags_prefix_hostid
        )
        zntsettings_tags = create_tags_list(
            _bool=data_zabbix.get('settings_zntsettingstag_bool') and body_messages_tags_trigger_settings,
            tag=data_zabbix['eventtags'],
            zntsettingstag=True
        )
        mentions = create_mentions_list(
            _bool=data_zabbix.get('settings_zntmentions_bool') and body_messages_mentions_settings,
            mentions=data_zabbix['eventtags']
        )
        
        # Формирование ссылок
        trigger_url = create_links_list(
            _bool=data_zabbix.get('settings_triggerlinks_bool') and body_messages_url_notes,
            url=data_zabbix.get('triggerurl'),
            _type=body_messages_url_emoji_notes
        )
        host_url = create_links_list(
            _bool=data_zabbix.get('settings_hostlinks_bool') and body_messages_url_host,
            url=zabbix_host_link.format(zabbix_server=zabbix_api_url.rstrip('/'), host=data_zabbix.get('host')),
            _type=body_messages_url_emoji_host
        )
        ack_url = create_links_list(
            _bool=data_zabbix.get('settings_acklinks_bool') and body_messages_url_ack,
            url=zabbix_ack_link.format(zabbix_server=zabbix_api_url.rstrip('/'), eventid=data_zabbix.get('eventid')),
            _type=body_messages_url_emoji_ack
        )
        event_url = create_links_list(
            _bool=data_zabbix.get('settings_eventlinks_bool') and body_messages_url_event,
            url=zabbix_event_link.format(
                zabbix_server=zabbix_api_url.rstrip('/'),
                eventid=data_zabbix.get('eventid'),
                triggerid=data_zabbix.get('triggerid')
            ),
            _type=body_messages_url_emoji_event
        )
        
        # Период графика
        graph_period = zabbix_graph_period_default
        if isinstance(zntsettings_tags, dict) and trigger_settings_tag_graph_period in ' '.join(zntsettings_tags.get(trigger_settings_tag, [])):
            try:
                for setting in zntsettings_tags.get(trigger_settings_tag, []):
                    if setting.startswith(f"{trigger_settings_tag_graph_period}="):
                        graph_period = int(setting.split('=')[1])
                        break
            except Exception as e:
                if loggings:
                    loggings.warning(f"Graph period parsing failed: {e}")
        
        if data_zabbix['graphs_period'] != 'default':
            try:
                graph_period = int(data_zabbix['graphs_period'])
            except ValueError:
                pass
        
        # Ссылки на графики
        url_list = []
        if trigger_url:
            url_list.append(trigger_url)
        for item_id in set([x for x in data_zabbix.get('itemid', '').split() if re.search(r"\d+", x)]):
            items_link = create_links_list(
                _bool=data_zabbix.get('settings_graphlinks_bool') and body_messages_url_graphs,
                url=zabbix_graph_link.format(
                    zabbix_server=zabbix_api_url.rstrip('/'),
                    itemid=item_id,
                    range_time=graph_period
                ),
                _type=body_messages_url_emoji_graphs
            )
            if items_link:
                url_list.append(items_link)
        if event_url:
            url_list.append(event_url)
        if ack_url:
            url_list.append(ack_url)
        if host_url:
            url_list.append(host_url)
        
        # Формирование графиков
        graphs_png = None
        graphs_name = body_messages_title.format(
            title=data_zabbix['title'],
            period_time=set_period_day_hour(graph_period)
        )
        
        if data_zabbix.get('settings_graphs_bool') and zabbix_graph:
            num_items_id = [item_id for item_id in data_zabbix['itemid'].split() if re.search(r"\d+", item_id)]
            if len(num_items_id) == 1:
                graphs_png = get_chart_png(
                    itemid=num_items_id[0],
                    graff_name=graphs_name,
                    period=graph_period
                )
            elif len(num_items_id) > 1:
                graphs_png_group = []
                for item_id in set([x for x in data_zabbix.get('itemid', '').split() if re.search(r"\d+", x)]):
                    chart = get_chart_png(itemid=item_id, graff_name=graphs_name, period=graph_period)
                    if chart and chart.get('img'):
                        graphs_png_group.append(InputMediaPhoto(media=chart['img']))
                graphs_png = graphs_png_group if graphs_png_group else None
        
        # Формирование сообщения
        subject = html.escape(args.subject.format_map(FailSafeDict(zabbix_status_emoji_map)))
        body = html.escape(data_zabbix['message'])
        if body_messages_cut_symbol and len(body) > body_messages_max_symbol:
            truncated = True
            body = body[:body_messages_max_symbol] + f' <a href="{zabbix_event_link.format(zabbix_server=zabbix_api_url.rstrip("/"), eventid=data_zabbix.get("eventid"), triggerid=data_zabbix.get("triggerid"))}">...</a>'
        else:
            truncated = False
        
        links = body_messages_url_delimiter.join(url_list) if body_messages_url and url_list else ''
        tags_list = [t for t in [event_tags, eventid_tags, itemid_tags, triggerid_tags, actionid_tags, hostid_tags] if t and t != body_messages_tags_no]
        tags = body_messages_tags_delimiter.join(tags_list) if body_messages_tags and tags_list else ''
        mentions_text = ' '.join(mentions) if mentions and body_messages_mentions_settings else ''
        
        message = body_messages.format(
            subject=subject,
            body=f'\n\n{body}' if body else '',
            links=f'\n{links}' if links else '',
            tags=f'\n\n{tags}' if tags else '',
            mentions=f'\n\n{mentions_text}' if mentions_text else ''
        )
        
        # Отправка сообщения
        await send_messages(
            bot=bot,
            sent_to=args.username,
            message=message,
            media_data=graphs_png,
            eventid=data_zabbix['eventid'],
            itemid=data_zabbix.get('itemid'),
            settings_keyboard=data_zabbix.get('settings_keyboard_bool'),
            disable_notification=False
        )
    
    finally:
        await bot_session.close()

# ==================== ТОЧКА ВХОДА ====================
if __name__ == "__main__":
    try:
        asyncio.run(main_async())
    except SystemExit as e:
        sys.exit(e.code)
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        if loggings:
            loggings.critical(f"Unhandled exception: {e}", exc_info=True)
        else:
            print(f"Critical error: {e}", file=sys.stderr)
        sys.exit(1)