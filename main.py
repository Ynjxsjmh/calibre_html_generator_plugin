import base64
import os
import re

import ebooklib

from ebooklib import epub
from bs4 import BeautifulSoup


def make_toc(toc: list, href2id: dict, level=0):
    lst = ''
    indent = '  ' * level
    for link in toc:
        if isinstance(link, epub.Link):
            href = href2id[link.href.split('#')[0]]
            item = f'{indent}<li><a id="toc_{href}" href="#{href}">{link.title}</a></li>'
            print(' '*level, link.title, href)
        elif isinstance(link, tuple):
            section, sub_toc = link
            href = href2id[section.href.split('#')[0]]
            print(' '*level, section.title, href)
            sub_item = make_toc(sub_toc, href2id, level+1)
            item = f'{indent}<li><a id="toc_{href}" href="#{href}">{section.title}</a>{sub_item}</li>'
        lst += indent + item + '\n'
    return f'\n{indent}<ul>\n{lst}{indent}</ul>\n'


def process_images(soup, img_tags):
    """
    处理 HTML 中的所有图片标签（`img`）。
    - 替换 `src` 属性。
    - 根据是否有 `class` 属性来设置 `style`。
    """
    for img_element in soup.find_all("img"):
        img_element['src'] = img_tags[os.path.basename(img_element['src'])]

        if img_element.get('class') is not None and img_element.parent.get('class') is not None:
            img_element['style'] = ""
            img_element.parent['style'] = "max-height: none"
        elif img_element.get('class') is not None:
            img_element['style'] = ""
        else:
            img_element['style'] = "width: auto; max-width: 100%; height: auto;"


def process_ids(soup, item_id):
    """
    为 HTML 中所有带有 `id` 属性的元素添加前缀，以确保 ID 的唯一性。
    """
    for id_element in soup.css.select('*[id]'):
        id_element['id'] = f"{item_id}_{id_element['id']}"


def process_hrefs(soup, href2id, item_id):
    """
    处理 HTML 中的所有链接（`href`）属性，将其转换为内部锚点链接。
    - 如果链接包含 `#`，则处理锚点。
    - 如果链接是文件路径，则转换为相应的 ID。
    """
    for href_element in soup.css.select('*[href]'):
        href = href_element['href']

        if '#' in href:
            href, anchor = href.split('#')
            if len(href) == 0:
                href_element['href'] = f'#{item_id}_{anchor}'
            else:
                href_element['href'] = '#' \
                    + ( href2id.get(href, None) \
                       or href2id.get(os.path.basename(href), None) or href ) \
                    + "_" + anchor
        elif (href in href2id) or (os.path.basename(href) in href2id):
            href_element['href'] = '#' \
                + ( href2id.get(href, None) \
                    or href2id.get(os.path.basename(href), None) )


def epub_to_html(epub_path, html_path):
    book: epub.EpubBook = epub.read_epub(epub_path)

    # html中所有的 href 属性的唯一标识
    href2id = {item.get_name(): item.get_id() for item in book.get_items()} \
        | {os.path.basename(item.get_name()): item.get_id() for item in book.get_items()}
    book_toc = make_toc(book.toc, href2id)

    img_tags = {}
    css_content = ""
    js_content = ""
    for item in book.get_items():
        item_type = item.get_type()
        item_name = item.get_name()
        if item_type == ebooklib.ITEM_IMAGE or item_type == ebooklib.ITEM_COVER:
            if not item_name.lower().endswith(('.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.gif')):
                print(f'{item_name} seems not like image')
                continue
            img_data = base64.b64encode(item.get_content()).decode("utf-8")
            img_base64_data = f'data:image/{item.media_type.split("/")[-1]};base64,{img_data}'
            img_href = item_name
            if img_href not in img_tags:
                img_tags[img_href] = img_base64_data
                img_tags[os.path.basename(img_href)] = img_base64_data
        elif item_type == ebooklib.ITEM_STYLE:
            css_content += item.get_content().decode('utf-8') + '\n'
        elif item_type == ebooklib.ITEM_SCRIPT:
            js_content += item.get_content().decode('utf-8') + '\n'

    css_content = f'<style>{css_content}</style>'
    js_content = f'<script>{js_content}</script>'

    book_content = ""
    for item_id, linear in book.spine:
        item = book.get_item_with_id(item_id) # 这里基本都是一章一章的，但是一章还可能会有子章节，目录怎么定位到子章节呢
        content = item.get_body_content().decode("utf-8")
        soup = BeautifulSoup(content, "html.parser")

        process_images(soup, img_tags)
        process_ids(soup, item_id)
        process_hrefs(soup, href2id, item_id)

        # 添加目录锚点
        book_content += f'<a id="{item_id}" href="#toc_{item_id}"></a>{soup.prettify()}'

    html_content = css_content + '\n' + book_toc + '\n' + book_content + '\n' + js_content
    with open(html_path, "w", encoding="utf-8") as html_file:
        html_file.write(html_content)

epub_path = r".\Tiny Experiments_ How to Live F - Anne-Laure Le Cunff.epub"
epub_to_html(epub_path, 'output.html')
