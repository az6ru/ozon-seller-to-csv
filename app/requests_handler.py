import datetime
import httpx
from enum import Enum
import asyncio
import json
import os
from pathlib import Path
from common import cookies_str_to_dict
from pydantic import BaseModel, Field
import re

# Удаляем загрузку переменных окружения, так как теперь будем использовать settings.txt
# load_dotenv()


# Функция для парсинга curl-команды из settings.txt
def parse_curl_command(file_path=None):
    """
    Парсит curl-команду из текстового файла и извлекает URL, заголовки и cookies.
    
    Args:
        file_path: Путь к файлу с curl-командой
        
    Returns:
        dict: Словарь с ключами 'url', 'headers', 'cookies' и 'base_url'
    """
    try:
        # Если путь не указан, ищем файл settings.txt
        if file_path is None:
            script_dir = Path(__file__).parent.parent
            file_path = script_dir / "docs" / "example" / "settings.txt"
            if not file_path.exists():
                # Если файл не найден, попробуем найти в корне проекта
                file_path = script_dir / "settings.txt"
        
        with open(file_path, 'r', encoding='utf-8') as f:
            curl_text = f.read().strip()
        
        # Извлекаем URL
        url_match = re.search(r"curl '([^']+)'", curl_text)
        if not url_match:
            url_match = re.search(r'curl "([^"]+)"', curl_text)
        
        if not url_match:
            raise ValueError("URL не найден в curl-команде")
            
        url = url_match.group(1)
        
        # Извлекаем базовый URL API
        base_url_parts = url.split('/api/')
        base_url = base_url_parts[0]
        api_path = f"/api/{base_url_parts[1].split('?')[0]}"
        
        # Извлекаем заголовки
        headers = {}
        header_matches = re.finditer(r"-H '([^:]+): ([^']+)'", curl_text)
        if not header_matches:
            header_matches = re.finditer(r'-H "([^:]+): ([^"]+)"', curl_text)
            
        for match in re.finditer(r"-H '([^:]+): ([^']+)'", curl_text):
            header_name = match.group(1)
            header_value = match.group(2)
            headers[header_name] = header_value
            
        # Извлекаем cookies
        cookies = {}
        cookie_match = re.search(r"-b '([^']+)'", curl_text)
        if not cookie_match:
            cookie_match = re.search(r'-b "([^"]+)"', curl_text)
            
        if cookie_match:
            cookie_string = cookie_match.group(1)
            cookies = dict(cookie.split('=', 1) for cookie in cookie_string.split('; '))
        
        return {
            'url': url,
            'base_url': base_url,
            'api_path': api_path,
            'headers': headers,
            'cookies': cookies
        }
    except Exception as e:
        print(f"Ошибка при парсинге curl-команды: {e}")
        return None

# Загружаем настройки из settings.txt
CURL_DATA = parse_curl_command()

# Если настройки не загрузились, используем пустые значения
if CURL_DATA is None:
    CURL_DATA = {
        'url': '',
        'base_url': '',
        'api_path': '',
        'headers': {},
        'cookies': {}
    }

# Получаем базовый домен для API
BASE_URL = CURL_DATA['base_url']
API_PATH = CURL_DATA['api_path']
HEADERS = CURL_DATA['headers']
COOKIES = CURL_DATA['cookies']


# типы запросов (изначально было не ясно какие будут нужны)
class RequestTypes(Enum):
    """
    Предусмотренные типы запросов
    """
    GET = 'get'
    POST = 'post'


# формат ответа функции
class Response(BaseModel):
    """
    Модель ответа после опроса ресурса
    """
    status: bool = Field(description='Статус успешного или неуспешного выполнения')
    object: str | dict | None = Field(description='Строка если возвращается страница или словарь если был обработан json')


def gen_params_for_items(input_url: str, page: int) -> dict| bool:
    """
    Формирование параметров запроса для получения товаров
    """
    try:
        url_splitted = input_url.split('/')
        id_seller = url_splitted[4].split('-')[1]
        return {
            "url": f"/seller/{url_splitted[4]}/{url_splitted[5]}/",
            "layout_container": "categorySearchMegapagination",
            "layout_page_index": "3",
            "miniapp": f"seller_{id_seller}",
            "page": str(page)
        }
    except Exception:
        return False


def gen_params_for_llc_info(input_url: str) -> dict | bool:
    """
    Формирование параметров запроса для получения информации ЮЛ
    """
    try:
        url_splitted = input_url.split('/')
        id_seller = url_splitted[4].split('-')[1]
    except Exception:
        return False
    return {
        "url": "/modal/shop-in-shop-info",
        "seller_id": str(id_seller),
        "page_changed": "true"
    }


def get_url_api(domain: str) -> str:
    """
    Формирование URL API с использованием базового домена из settings.txt
    """
    base_url = f"https://{domain}"
    if BASE_URL:
        base_url = BASE_URL
    
    api_path = CURL_DATA.get('api_path') or "/api/entrypoint-api.bx/page/json/v2"
    return f"{base_url}{api_path}"


async def send_request(cookies_str: str = None, headers=None, type_: RequestTypes = RequestTypes.GET,
                       url: str = None, params: dict = None, data: dict = None, json_loads: bool = True,
                       max_attempts: int = 5, domain: str = None) -> Response | None:
    """
    Отправка запроса (дефолтная функция)
    :param cookies_str: куки в формате строки (если None, используются куки из settings.txt)
    :param headers: заголовки (если None, используются заголовки из settings.txt)
    :param type_: тип запроса гет/пост
    :param url: адрес
    :param params: параметры
    :param data: тело запроса
    :param json_loads: флажок конвертации json в объект пайтон
    :param max_attempts: число попыток
    :param domain: домен для запросов по апи
    :return: статус + данные
    """
    # предварительная подготовка заголовков, куки, тела запроса
    if headers is None:
        headers = HEADERS
    
    # Используем куки из settings.txt, если не переданы явно
    if cookies_str is not None:
        cookies_dict = cookies_str_to_dict(cookies_str)
    else:
        cookies_dict = COOKIES
    
    if data is not None:
        data_json = json.dumps(data)
    else:
        data_json = None
    
    if url is None:
        url = get_url_api(domain)
    
    # инициализация асинхронного клиента с настройками
    client_params = {
        'cookies': cookies_dict,
        'headers': headers,
        'follow_redirects': True,
        'timeout': 30.0,
        'http2': True,
    }
    
    async with httpx.AsyncClient(**client_params) as client:
        while True:
            # проверка на число ошибок
            max_attempts -= 1
            if max_attempts <= 0:
                return Response(status=False, object=None)
            # запрос
            try:
                if type_ == RequestTypes.GET:
                    r = await client.get(url, params=params, timeout=120)
                elif type_ == RequestTypes.POST:
                    r = await client.post(url, params=params, data=data_json, timeout=120)
                print(f'{datetime.datetime.now()} status_code: {r.status_code}')
            except Exception as e:
                print(f"Ошибка запроса: {e}")
                return Response(status=False, object=None)
            # распознавание кодов ответа сервера
            if 200 <= r.status_code <= 299:
                # конвертация json в объект
                if json_loads is True:
                    try:
                        r_object = json.loads(r.text)
                    except Exception:
                        r_object = None
                else:
                    r_object = r.text
                return Response(status=True, object=r_object)
            elif 300 <= r.status_code <= 400:
                return Response(status=False, object=None)
            elif 500 <= r.status_code <= 599:
                await asyncio.sleep(5)
                continue
            else:
                return Response(status=False, object=None)
