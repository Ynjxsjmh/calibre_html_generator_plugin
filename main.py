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
            href = href2id[link.href]
            item = f'{indent}<li><a id="toc_{href}" href="#{href}">{link.title}</a></li>'
            print(' '*level, link.title, href2id[link.href])
        elif isinstance(link, tuple):
            section, sub_toc = link
            href = href2id[section.href]
            print(' '*level, section.title, href2id[section.href])
            sub_item = make_toc(sub_toc, href2id, level+1)
            item = f'{indent}<li><a id="toc_{href}" href="#{href}">{section.title}</a>{sub_item}</li>'
        lst += indent + item + '\n'
    return f'\n{indent}<ul>\n{lst}{indent}</ul>\n'


def epub_to_html(epub_path, html_path):
    book: epub.EpubBook = epub.read_epub(epub_path)

    href2id = {item.get_name(): item.get_id() for item in book.get_items()} \
        | {os.path.basename(item.get_name()): item.get_id() for item in book.get_items()}
    book_toc = make_toc(book.toc, href2id)

    img_tags = {}
    css_content = ""
    js_content = ""
    for item in book.get_items():
        item_type = item.get_type()
        if item_type == ebooklib.ITEM_IMAGE:
            img_data = base64.b64encode(item.get_content()).decode("utf-8")
            img_base64_data = f'data:image/{item.media_type.split("/")[-1]};base64,{img_data}'
            img_href = item.get_name()
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

        # 替换 img
        for img_element in soup.find_all("img"):
            img_element['src'] = img_tags[os.path.basename(img_element['src'])]
            if img_element['class'] is not None:
                img_element['style'] = ""
            else:
                img_element['style'] = "width: auto; max-width: 100%; height: auto;"

        # 替换 href
        for id_element in soup.css.select('*[id]'):
            id_element['id'] = item_id + '_' + id_element['id']

        for href_element in soup.css.select('*[href]'):
            href = href_element['href']

            if '#' in href:
                href, anchor = href.split('#')
                href_element['href'] = '#' \
                    + ( href2id.get(href, None) \
                       or href2id.get(os.path.basename(href), None) or href ) \
                    + "_" + anchor
            elif (href in href2id) or (os.path.basename(href) in href2id):
                href_element['href'] = '#' \
                    + ( href2id.get(href, None) \
                        or href2id.get(os.path.basename(href), None) )

        # 添加目录锚点
        book_content += f'<a id="{item_id}" href="#toc_{item_id}"></a>{soup.prettify()}'

    html_content = css_content + '\n' + book_toc + '\n' + book_content + '\n' + js_content
    with open(html_path, "w", encoding="utf-8") as html_file:
        html_file.write(html_content)

epub_path = r".\Tiny Experiments_ How to Live F - Anne-Laure Le Cunff.epub"
epub_to_html(epub_path, 'output.html')
