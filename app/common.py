import json
import traceback
import datetime
import pandas as pd
import numpy as np
from bs4 import BeautifulSoup
from pydantic import BaseModel, HttpUrl, model_validator
from errors import InputValidationError
import os
from pathlib import Path


class URLModel(BaseModel):
    """
    Модель-валидатор вводимого адреса
    """
    text: HttpUrl

    @model_validator(mode='after')
    def add_check(self):
        words = ('ozon', 'seller', 'products')
        if not all(word in str(self.text) for word in words):
            raise InputValidationError(f'URL должен содержать слова: {words}')
        return self


def generate_list_pages(from_: int, to_: int, chunk_size: int) -> [int]:
    """
    Генерация списка запросов
    """
    numbers = list(range(from_, to_))
    return [numbers[i:i + chunk_size] for i in range(0, len(numbers), chunk_size)]


def cookies_str_to_dict(cookies_str: str) -> dict:
    """
    Конвертация куки в формат словаря
    """
    try:
        cookies_list = cookies_str.split('; ')
        cookies_dict = {}
        for cookie in cookies_list:
            cook_list = cookie.split('=')
            cookies_dict[cook_list[0]] = cook_list[1]
        return cookies_dict
    except Exception:
        return {}


def change_category_in_url(url: str, category: str) -> str | bool:
    """
    Изменение категории в переменной адреса
    """
    url_splitted = url.split('/')
    url_splitted.pop(5)
    url_splitted.insert(5, category)
    url_str = ''
    for i in url_splitted:
        url_str += i + '/'
    return url_str[:-1]


def check_domain_in_url(url: str):
    """
    Извлечение домена
    """
    url_splitted = url.split('/')
    return url_splitted[2]


def get_seller_id_from_url(url: str) -> str | bool:
    """
    Извлечение идентификатора продавца из адреса
    """
    url_splitted = url.split('/')
    return url_splitted[4]


def edit_get_items_list(data: dict) -> list | bool | None:
    """
    Первичное редактирование (извлечение) сырых данных по товарам + проверка на успешный сбор
    """
    # проверка на успешный сбор
    success = data.get('layout')
    if not success:
        return None
    try:
        key_data = data['layout'][0]['stateId']
        items_str = data['widgetStates'][key_data]
        items_object = json.loads(items_str)
        items_list = items_object['items']
        return items_list
    except Exception:
        traceback.print_exc()
        return False


def edit_items_to_df(main_items_dict: dict, llc_info: str, seller_id: str) -> pd.DataFrame | bool:
    """
    Финальный сбор данных в дата-фрейм с сортировкой
    """
    # формирование даты сбора
    dt = str(datetime.datetime.now().replace(microsecond=0))
    # создание дата-фрейма с нужными полями
    df = pd.DataFrame({'shop': [], 'datetime': [], 'price_reg': [], 'price_promo': [],
                       'article': [], 'name': [], 'category_path': []})
    try:
        # перебор категорий с подготовленными списками словарей
        for name_cat, items_list in main_items_dict.items():
            # перебор товаров
            for item in items_list:
                # определение артикула
                article = item.get('skuId')
                main_state = item.get('mainState')
                price_promo, price_reg, name = None, None, None
                try:

                    # перебор нужных данных для извлечения цен
                    for row in main_state:
                        if row.get('id') == 'atom':
                            prices_data = row['atom']['priceV2']['price']
                            # редактирование для нужного формата целого числа
                            maketrans = str.maketrans({'₽': '', '₾': '', '\u2009': '', ' ': '', ',': '.'})
                            price_promo = int(float(prices_data[0]['text'].translate(maketrans)))
                            price_reg = int(float(prices_data[1]['text'].translate(maketrans)))
                            break
                except Exception:
                    pass
                try:
                    # перебор для извлечения наименования
                    for row in main_state:
                        if row.get('id') == 'name':
                            name = row['atom']['textAtom']['text']
                            break
                except Exception:
                    pass
                # в случае если не были собраны данные по ЮЛ, вставляем идентификатор продавца
                if llc_info == False:
                    llc_info = seller_id
                # добавляем строку с данными по товару
                df.loc[len(df)] = [llc_info, dt, price_reg, price_promo, article, name, name_cat]
        # сортируем по категориям и цене
        df = df.sort_values(by=['category_path', 'price_promo'], ascending=[True, False])
        print(df.to_string())
    except Exception:
        return False
    return df


def edit_llc_info(data: dict) -> str | bool:
    """
    Извлекаем данные по ЮЛ
    """
    try:
        info_str = data['widgetStates']['textBlock-3252445-default-1']
        info_object = json.loads(info_str)
        info = info_object['body'][0]['textAtom']['text']
        info_formatted = info.replace('<br>', ' ')
        return info_formatted
    except Exception:
        return False


def edit_categories(response_text: str) -> dict | bool:
    """
    Редактируем категории
    """
    try:
        soup = BeautifulSoup(response_text, "html.parser")
        # находим нужный блок коде страницы
        div = soup.find("div", {"id": "state-filtersDesktop-3124459-default-1"})
        data_state = div.get("data-state")
        data_state = data_state.replace("\'", '')
        # загружаем текст как объект и берем нужный ключ
        parsed_data = json.loads(data_state)
        categories_data = parsed_data['sections'][0]['filters'][0]['categoryFilter']['categories']
        cat_dict = {}
        # перебираем категории которые являются основными
        for category in categories_data:
            if category['level'] == 0:
                cat_dict[category['title']] = category['urlValue'].split('/')[3]
        return cat_dict
    except Exception:
        traceback.print_exc()
        return False


def save_csv(df: pd.DataFrame, seller_id: str) -> bool:
    """
    Сохранение документа csv
    """
    try:
        # Создаем директорию для отчетов, если её нет
        reports_dir = Path(__file__).parent / "reports"
        reports_dir.mkdir(exist_ok=True)
        
        # Сохраняем отчет
        df.to_csv(f'{reports_dir}/{seller_id}_{datetime.datetime.now().replace(microsecond=0)}.csv', index=False)
        return True
    except Exception as e:
        print(f"Ошибка при сохранении CSV: {e}")
        return False
