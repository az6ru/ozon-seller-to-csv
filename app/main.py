import datetime
import os
# Удаляем загрузку переменных окружения
# from dotenv import load_dotenv
from common import edit_llc_info, edit_items_to_df, edit_get_items_list, edit_categories, generate_list_pages, \
    change_category_in_url, get_seller_id_from_url, save_csv, check_domain_in_url, URLModel
from requests_handler import gen_params_for_llc_info, send_request, gen_params_for_items
import asyncio
from errors import GetDataError, EditDataError

# загрузка переменных для окружения больше не нужна
# load_dotenv()

# загрузка куки больше не нужна, так как они берутся из settings.txt
# COOKIES = os.getenv('COOKIES')


async def get_all_items_ozon(input_url: str) -> bool:
    """
    Основная функция полного цикла сбора
    """
    # запуск
    start_dt = datetime.datetime.now()
    print(f'{start_dt} START!')

    # проверка ссылки
    try:
        validate_url = URLModel(**{'text': input_url})
    except Exception as e:
        print(e)
        return False

    # взятие домена для запросов
    domain = check_domain_in_url(input_url)

    # формирование параметров для запроса ЮЛ
    params_llc = gen_params_for_llc_info(input_url)
    # создание и получение 2 задач: данные по ЮЛ, данные по категориям
    tasks = (send_request(params=params_llc, domain=domain),
             send_request(url=input_url, json_loads=False))
    responses_list = await asyncio.gather(*tasks)
    # если данных по категориям нет, то далее выполнение невозможно
    # (можно сделать Намного более гибкие обработчики ошибок)
    if not responses_list[0].status or not responses_list[1].status:
        raise GetDataError()

    # редактирование данных по ЮЛ и категориям
    llc_info = edit_llc_info(responses_list[0].object)
    categories_list = edit_categories(responses_list[1].object)
    if not categories_list:
        raise EditDataError()

    # общий словарь для наполнения сырыми данными
    main_items_dict = {}
    # перебираем категории ЮЛ
    for name_cat, url_cat in categories_list.items():
        main_items_dict[name_cat] = []
        # флаг сбора данных включен
        cat_parse = True
        # меняем категорию в адресе
        input_url_upd_cat = change_category_in_url(input_url, url_cat)
        # формируем список числа запросов, по 3 за раз по умолчанию
        list_pages = generate_list_pages(1, 20, 3)
        # проверка флага парсинга
        for chunk in list_pages:
            if cat_parse is False:
                break
            # формируем параметры запросов
            # (универсальный способ)
            params_list = [gen_params_for_items(input_url_upd_cat, page) for page in chunk]
            # создание и получение данных асинхронно
            tasks = (send_request(params=params, domain=domain) for params in params_list)
            responses_list = await asyncio.gather(*tasks)
            # проверка есть ли хоть в 1 запросе данные
            if all(response.status is False for response in responses_list):
                raise GetDataError()
            # первично обрабатываем и определяем наличие нужных данных
            items_lists = [edit_get_items_list(response.object) for response in responses_list]
            # если нигде нет данных убираем флаг дальнейших запросов
            if any(item is None for item in items_lists):
                cat_parse = False
            # обновляем общий список с первичными данными
            main_items_dict[name_cat].extend([item for sublist in items_lists if sublist is not None for item in sublist])

    # получаем идентификатор продавца
    seller_id = get_seller_id_from_url(input_url)
    # финально обрабатываем данные и формируем дата-фрейм
    df = edit_items_to_df(main_items_dict, llc_info, seller_id)
    # сохраняем csv
    status = save_csv(df, seller_id)

    # отображаем цикл завершения и подсчитываем время
    end_dt = datetime.datetime.now()
    if status:
        print(f'{end_dt} DONE!\nSPENT {end_dt - start_dt}')
    else:
        print(f'{end_dt} ERROR!')
    return True


if __name__ == '__main__':
    # запускаем бесконечный цикл (для удобства ручного тестирования)
    while True:
        input_url = input('Введите url формата "https://www.ozon.ru/seller/webmarket-150120/products/?miniapp=seller_150120"\n')
        asyncio.run(get_all_items_ozon(input_url))
