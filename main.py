import os
import re
from urllib.parse import urljoin

import pypandoc
from tqdm import tqdm
from requests import Session, Response
from bs4 import BeautifulSoup
from bs4.element import Tag
from dotenv import load_dotenv

load_dotenv()
LOGIN = os.getenv('LOGIN')
PASSWORD = os.getenv('PASSWORD')

BASE_URL = 'http://localhost'
NODE_LIST_URL = urljoin(BASE_URL, '/?q=admin/content/node&page=%d')
NUM_PAGES = 57
AUTH_URL = urljoin(BASE_URL, '/?q=node/100&destination=node/100')
CONTENT_TYPES_LIST_URL = urljoin(BASE_URL, '/?q=admin/content/types')
AUTH_DATA = {'name': LOGIN, 'pass': PASSWORD, 'form_id': 'user_login_block', 'op': 'Вход+в+систему',
             'form_build_id': 'form-wbr8299J4ABONGV6xQSbNLtC2kSDLoMIn3oPBgP2Byo',
             'openid_identifier': '',
             'openid.return_to': 'http://localhost/?q=openid/authenticate&destination=node%2F100'}

EXPORT_PATH = './export'
FILE_NAME_FORMAT = '{page_number}_{content_type}_{page_name}'
EXPORT_FORMAT = '.docx'


def check_if_requests_succeed(response: Response) -> None:
    assert response.status_code == 200, \
        f'Request to "{response.url}" failed: {response.status_code} {response.reason}'


def sanitize_file_name(name: str) -> str:
    return re.sub('[\\\\/:*?\"<>|]', ' ', name)[:100]


def get_content_table_from(s: Session, url: str) -> Tag:
    response = s.get(url)
    check_if_requests_succeed(response)
    return BeautifulSoup(response.text, features='html.parser').find('table', attrs={
        'class': 'sticky-enabled'})


def process_list_page(list_page_number: int) -> None:
    node_list = get_content_table_from(session, NODE_LIST_URL % list_page_number)
    for row in tqdm(node_list.find_all('tr'), desc='nodes'):
        process_node(row)


def process_node(row: Tag, skip_if_exist=True) -> None:
    link_element = row.find('a')
    if link_element is not None:
        link = link_element.get('href')
        page_name = link_element.text
        content_type = content_types[link_element.find_next('td').text]
        page_number = os.path.split(link)[-1]

        file_name = os.path.join(EXPORT_PATH,
                                 sanitize_file_name(
                                     FILE_NAME_FORMAT.format(page_number=page_number,
                                                             content_type=content_type,
                                                             page_name=page_name))) + EXPORT_FORMAT

        if skip_if_exist and os.path.exists(file_name):
            return

        page_response = session.get(urljoin(BASE_URL, link))
        check_if_requests_succeed(page_response)
        page_parser = BeautifulSoup(page_response.text, features='html.parser')

        # Вытаскиваем содержимое страницы, игнорируя header, footer и прочие части сайта
        page_content = page_parser.find('div', attrs={'class': 'node'}) \
            .find('div', attrs={'class': 'content'})

        # Исправляем относительные ссылки на изображения на абсолютные
        for image in page_content.find_all('img'):
            if not image['src'].startswith('http'):
                image['src'] = urljoin(BASE_URL, image['src'])

        # Удаление ненужных элементов интерфейса со страницы
        navigation = page_content.find('div', attrs={'class': 'book-navigation'})
        if navigation is not None:
            navigation.decompose()

        pypandoc.convert_text(
            str(page_content), EXPORT_FORMAT[1:], 'html', outputfile=file_name)


if __name__ == '__main__':
    if not os.path.exists(EXPORT_PATH):
        os.mkdir(EXPORT_PATH)

    with Session() as session:
        # Вход в аккаунт администратора
        auth_response = session.post(AUTH_URL, data=AUTH_DATA)
        check_if_requests_succeed(auth_response)
        assert session.cookies, 'Session cookies was not set'

        # Получение списка внутренних (коротких) имён типов материалов
        content_types = {}
        content_type_list = get_content_table_from(session, CONTENT_TYPES_LIST_URL)
        content_type_list.find()
        for ctype_row in content_type_list.find_all('tr'):
            full_name = ctype_row.find('td')
            if full_name is not None:
                content_types[full_name.text] = full_name.find_next('td').text

        for page_num in tqdm(range(NUM_PAGES), desc='list pages'):
            process_list_page(page_num)
