# -*- coding: utf-8 -*-

#  Licensed under the Apache License, Version 2.0 (the 'License'); you may
#  not use this file except in compliance with the License. You may obtain
#  a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an 'AS IS' BASIS, WITHOUT
#  WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#  License for the specific language governing permissions and limitations
#  under the License.

from __future__ import unicode_literals

import errno
import os
import datetime
import time
import glob
import sys
import tempfile
import random
import psycopg2
import boto3
import neologdn
import urllib.parse
import urllib.request
from PIL import Image
from argparse import ArgumentParser
from bs4 import BeautifulSoup
from flask import Flask, request, abort
from linebot import (
    LineBotApi, WebhookHandler
)
from linebot.exceptions import (
    InvalidSignatureError
)
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    SourceUser, SourceGroup, SourceRoom,
    TemplateSendMessage, ConfirmTemplate, MessageTemplateAction,
    ButtonsTemplate, ImageCarouselTemplate, ImageCarouselColumn, URITemplateAction,
    PostbackTemplateAction, DatetimePickerTemplateAction,
    CarouselTemplate, CarouselColumn, PostbackEvent,
    StickerMessage, StickerSendMessage, LocationMessage, LocationSendMessage,
    ImageMessage, VideoMessage, AudioMessage, FileMessage,
    UnfollowEvent, FollowEvent, JoinEvent, LeaveEvent, BeaconEvent, ImageSendMessage
)

app = Flask(__name__)

# get CHANNEL_SECRET and CHANNEL_ACCESS_TOKEN from your environment variable
CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET', None)
CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', None)
if CHANNEL_SECRET is None:
    print('Specify LINE_CHANNEL_SECRET as environment variable.')
    sys.exit(1)
if CHANNEL_ACCESS_TOKEN is None:
    print('Specify LINE_CHANNEL_ACCESS_TOKEN as environment variable.')
    sys.exit(1)

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

AP_URL = 'https://nekobot-line.herokuapp.com'
DB_URL = os.getenv('DATABASE_URL', None)

AWS_S3_BUCKET_NAME = 'nekobot'
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID', None)
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY', None)

USER_ID_YOSHI = 'U35bca0dfb497d294737b7b25f4261a0b'

static_tmp_path = os.path.join(os.path.dirname(__file__), 'static', 'tmp')


class Intent:
    def __init__(self, target_text):
        self.match = False
        self.text = target_text
        self.id = 0
        self.name = ''
        self.example = ''
        self.weight = 0
        self.position = 0

    def reset_text(self, target_text):
        self.text = target_text
        return self

    def check_intent(self, exact_match=False):

        if exact_match:
            sql = 'SELECT id, name, example, weight, POSITION(example IN %s) '\
                'FROM public.intents '\
                'WHERE example = %s '\
                'ORDER BY weight DESC;'

        else:
            sql = 'SELECT id, name, example, weight, POSITION(example IN %s) '\
                'FROM public.intents '\
                'WHERE 0 < POSITION(example IN %s) '\
                'ORDER BY weight DESC;'

        with psycopg2.connect(DB_URL) as conn:
            with conn.cursor() as curs:

                curs.execute(sql, (self.text, self.text,))
                if 0 < curs.rowcount:
                    intent = curs.fetchone()
                    self.match = True
                else:
                    intent = (0, 'Unknown', '', 0, 0)

        (self.id, self.name, self.example, self.weight, self.position) = intent
        return self


class Entity:
    def __init__(self, target_text):
        self.match = False
        self.text = target_text
        self.id = 0
        self.name = ''
        self.synonym = ''
        self.weight = 0
        self.position = 0
        self.category = ''

    def reset_text(self, target_text):
        self.text = target_text
        return self

    def check_entity(self, exact_match=False):

        if exact_match:
            sql = 'SELECT id, name, synonym, weight, POSITION(synonym IN %s) '\
                    'FROM public.entities '\
                    'WHERE synonym = %s '\
                    'ORDER BY weight DESC;'

        else:
            sql = 'SELECT id, name, synonym, weight, POSITION(synonym IN %s) '\
                    'FROM public.entities '\
                    'WHERE 0 < POSITION(synonym IN %s) '\
                    'ORDER BY weight DESC;'

        with psycopg2.connect(DB_URL) as conn:
            with conn.cursor() as curs:

                curs.execute(sql, (self.text, self.text,))
                if 0 < curs.rowcount:
                    entity = curs.fetchone()
                    self.match = True
                else:
                    entity = (0, 'Unknown', '', 0, 0)

        (self.id, self.name, self.synonym, self.weight, self.position) = entity
        self.category = self._get_category()
        return self

    def _get_category(self):
        
        sql = 'SELECT name '\
                'FROM public.categories '\
                'WHERE entity = %s '\
                'ORDER BY RANDOM() ;'
        
        if self.match:

            with psycopg2.connect(DB_URL) as conn:
                with conn.cursor() as curs:

                    curs.execute(sql, (self.name, ))
                    if 0 < curs.rowcount:
                        (category,) = curs.fetchone()
                    else:
                        category = 'Unknown'

        else:
            category = 'Unknown'

        return category


class Setting():

    _sql_select = 'SELECT value '\
                    'FROM public.settings '\
                    'WHERE name = %s ;'

    _sql_update = 'UPDATE public.settings '\
                    'SET value = %s '\
                    'WHERE name = %s ;'

    def __init__(self):

        self.enable_access_management = self._get_enable_access_management()
        self.admin_line_users = self._get_admin_line_users()
        self.current_upload_category = self._get_current_upload_category()

    def _get_enable_access_management(self):
        with psycopg2.connect(DB_URL) as conn:
            with conn.cursor() as curs:

                curs.execute(self._sql_select, ('enable_access_management',))
                if 0 < curs.rowcount:
                    (enable_access_management,) = curs.fetchone()
                else:
                    enable_access_management = 'True'

        return enable_access_management

    def _get_admin_line_users(self):
        with psycopg2.connect(DB_URL) as conn:
            with conn.cursor() as curs:

                curs.execute(self._sql_select, ('admin_line_user',))
                if 0 < curs.rowcount:
                    admin_line_users_tp = curs.fetchall()

                    admin_line_users = []
                    for admin_line_user in admin_line_users_tp:
                        admin_line_users.append(admin_line_user[0].strip())

                else:
                    admin_line_users = []

        return admin_line_users

    def _get_current_upload_category(self):
        with psycopg2.connect(DB_URL) as conn:
            with conn.cursor() as curs:

                curs.execute(self._sql_select, ('current_upload_category',))
                if 0 < curs.rowcount:
                    (current_upload_category,) = curs.fetchone()
                else:
                    current_upload_category = ''

        return current_upload_category

    def update_enable_access_management(self,value):
        with psycopg2.connect(DB_URL) as conn:
            with conn.cursor() as curs:

                curs.execute(self._sql_update, (value, 'enable_access_management',))
                conn.commit()

        self.enable_access_management = self._get_enable_access_management()

        return self

    def update_current_upload_category(self,value):
        with psycopg2.connect(DB_URL) as conn:
            with conn.cursor() as curs:

                curs.execute(self._sql_update, (value, 'current_upload_category',))
                conn.commit()

        self.current_upload_category = self._get_current_upload_category()

        return self

    def check_admin_line_user(self, line_user_id):
        ret = False
        for admin_line_user in self.admin_line_users:
            if line_user_id == admin_line_user:
                ret = True
                break

        return ret

    def check_access_allow(self, line_user_id):
        ret = False
        if self.enable_access_management == 'False':
            ret = True
        elif self.enable_access_management == 'True':
            ret = self.check_admin_line_user(line_user_id)
        else:
            ret = False
        
        return ret

class _Tabelog_Value:
    def __init__(self):
        self.name=''
        self.image_key = ''
        self.url = ''
        self.score = 0.00
        self.station = ''
        self.genre = ''
        self.hours = ''

    def _set_value_tp(self, value_tp):
        self.name = value_tp[0]
        self.image_key = value_tp[1]
        self.url = value_tp[2]
        self.score = value_tp[3]
        self.station = value_tp[4]
        self.genre = value_tp[5]
        self.hours = value_tp[6]
        return self

    def _get_value_tp(self):
        return (self.name,self.image_key,self.url,self.score,self.station,self.genre,self.hours)

class _Tabelog_Insert:
    _DOMAIN = ('tabelog.com', 's.tabelog.com')
    _PATH_DIR_LEVEL = 5

    def __init__(self):
        self.value = _Tabelog_Value()
        self.url = ''

    def set_target_url(self,target_url):
        self.url = target_url
        if self.is_tabelog_domain():
            self.url = self._normalize_tabelog_url(self.url)
        else:
            self.url = ''

        return self

    def is_tabelog_domain(self):
        url_parse = urllib.parse.urlparse(self.url)
        if url_parse.netloc in self._DOMAIN:
            return True
        else:
            return False
    
    def url_exists(self):
        sql = 'SELECT name \
                FROM public.tabelog \
                WHERE url = %s;'
                
        with psycopg2.connect(DB_URL) as conn:
            with conn.cursor() as curs:

                curs.execute(sql, (self.url,))
                if 0 < curs.rowcount:
                    return True
                else:
                    return False
    
    def _normalize_tabelog_url(self,url):
        urln = url
        url_parse = urllib.parse.urlparse(url)

        if url_parse.netloc != self._DOMAIN[0]:
            netlocn = self._DOMAIN[0]
            urln = urln.replace(url_parse.netloc, netlocn)

        if url_parse.path.count('/') > self._PATH_DIR_LEVEL:
            ps = url_parse.path.split('/')
            pathn = '/' + ps[1] + '/' + ps[2] + '/' + ps[3] + '/' + ps[4] + '/'
            urln = urln.replace(url_parse.path, pathn)

        return urln

    def insert_tabelog_link(self):
        
        self.value._set_value_tp(self._tabelog_scraping())

        sql = 'INSERT INTO public.tabelog(\
                name, image_key, url, score, station, genre, hours) \
                VALUES (%s, %s, %s, %s, %s, %s, %s);'
                
        with psycopg2.connect(DB_URL) as conn:
            with conn.cursor() as curs:

                curs.execute(sql, self.value._get_value_tp())
                conn.commit()

        print('[Event Log]'
            + ' insert_tabelog_link'
            + ' values=('
            + str(self.value.name) + ', '
            + str(self.value.image_key) + ', '
            + str(self.value.url) + ', '
            + str(self.value.score) + ', '
            + str(self.value.station) + ', '
            + str(self.value.genre) + ', '
            + str(self.value.hours) + ')'
        )

        return self

    def _normalize_hours(self, hours):
        hoursn = hours
        hoursn = hoursn.replace('～', '-')
        hoursn = hoursn.replace('・','･')
        hoursn = neologdn.normalize(hoursn)
        hoursn = hoursn[:100]
        return hoursn
    
    def _tabelog_scraping(self):
        url = self.url
        html = urllib.request.urlopen(self.url).read()
        soup = BeautifulSoup(html, 'html.parser')

        #name
        name = soup.find(class_='display-name').span.string.strip()
        name = name.strip()

        #score
        score = float(soup.find(class_='rdheader-rating__score-val-dtl').string)

        #station
        station = soup.find(class_='rdheader-subinfo__item rdheader-subinfo__item--station').find(class_='linktree__parent-target-text').string
        station = station.strip()

        #genre,hour
        genre = ''
        hours = ''
        rstinfo_tables = soup.find_all('table', class_='c-table c-table--form rstinfo-table__table')
        for rstinfo_table in rstinfo_tables:
            rows = rstinfo_table.find_all('tr')
            for row in rows:
                if row.find('th').string == 'ジャンル':
                    genre = row.find('span').string
                elif row.find('th').string == '営業時間':
                    lines = row.find_all('p')
                    for line in lines:
                        hours += line.text + ' '

        genre = genre.strip()
        hours = self._normalize_hours(hours)

        #image_key
        image_key = 'nekobot/tabelog/tabelog_default.jpg'

        return (name, image_key, url, score, station, genre, hours,)
        

class _Tabelog_Select:
    _LIMIT = 6

    def __init__(self):
        self.values = []
        self.selected_count = 0

    def select_tanelog_links(self):

        sql = 'SELECT name, image_key, url, score, station, genre, hours \
	           FROM public.tabelog \
               ORDER BY RANDOM() \
               LIMIT %s ;'
        
        with psycopg2.connect(DB_URL) as conn:
            with conn.cursor() as curs:

                curs.execute(sql, (self._LIMIT,))
                self.selected_count = curs.rowcount
                if 0 < self.selected_count:
                    values = curs.fetchall()
                else:
                    values = []
                    
        for value in values:
            self.values.append(_Tabelog_Value()._set_value_tp(value))

        return self

    def _tabelog_action_text(self):
        text = random.choice([
            '猫', 'ねこ', 'ネコ', 'cat', 'neko', 'ひめ','ちゅーる'
        ])
        return text

    def carousel_columns(self):
        columns = []
        for value in self.values:
            columns.append(
                CarouselColumn(
                    thumbnail_image_url=my_s3_link_url(value.image_key),
                    title=(value.name + ' (' + '{:.2f}'.format(value.score) + ')')[:40],
                    text=(value.station + '\n' + value.genre)[:60],
                    actions=[
                        URITemplateAction(
                            label='食べログを見る', uri=value.url),
                        MessageTemplateAction(
                            label='ここにする！', text='ここで！\n' + value.url),
                        MessageTemplateAction(
                            label='ねこ', text=self._tabelog_action_text()),
                    ]
                )
            )

        return columns


class Tabelog:

    def __init__(self):
        self.insert = _Tabelog_Insert()
        self.select = _Tabelog_Select()


def my_normalize(text):
    text = neologdn.normalize(text)
    text = text.replace(' ', '')
    text = text.replace('〜', 'ー')
    text = text.replace('!', '')
    text = text.replace('?', '')
    text = text.replace('、', '')
    text = text.replace('。', '')
    text = text.lower()

    return text


def text_send_messages_db(entity,prefix='',suffix=''):
    
    sql = 'SELECT DISTINCT ON (reply_order) text, reply_order '\
            'FROM public.replies '\
            'WHERE entity = %s '\
            'ORDER BY reply_order ASC, RANDOM() ;'
    
    if entity.match:
        with psycopg2.connect(DB_URL) as conn:
            with conn.cursor() as curs:

                curs.execute(sql, (entity.name, ))
                if 0 < curs.rowcount:
                    reply_texts_tp = curs.fetchall()

                    reply_texts = []
                    for reply_text in reply_texts_tp:
                        reply_texts.append(reply_text[0].strip())

                else:
                    reply_texts = []

    else:
        reply_texts = []

    messages = []
    for reply_text in reply_texts:
        messages.append(TextSendMessage(text=prefix + reply_text + suffix))

    return messages


def genelate_image_url_s3(category):

    s3 = boto3.resource('s3')
    bucket = s3.Bucket(AWS_S3_BUCKET_NAME)

    obj_collections = bucket.objects.filter(Prefix=category)
    keys = [obj_summary.key for obj_summary in obj_collections if obj_summary.key.endswith('.jpg')]

    image_key = random.choice(keys)
    thumb_key = os.path.join('thumb', image_key)

    print('[Image Log] genelate_image_url_s3'
        + ' random_choice'
        + ' image_key=' + image_key
        + ' thumb_key=' + thumb_key
    )

    # #サムネイルが無ければ作成
    # if not exist_key_s3(thumb_key):
    #     thumb_path = download_from_s3(image_key)
    #     thumb_path = shrink_image(thumb_path, thumb_path, 240, 240)
    #     thumb_key = upload_to_s3(thumb_path, thumb_key)

    #     print('[Image Log] genelate_image_url_s3'
    #         + ' create_thumb'
    #         + ' thumb_path=' + thumb_path
    #     )
    # else:
    #     print('[Image Log] genelate_image_url_s3'
    #         + ' exist_thumb'
    #     )
        
    image_url = my_s3_presigned_url(image_key)
    thumb_url = my_s3_presigned_url(thumb_key)

    print('[Image Log] genelate_image_url_s3'
        + ' generate_presigned_url'
        + ' image_url=' + image_url
        + ' thumb_url=' + thumb_url
    )

    return image_url, thumb_url

def my_s3_presigned_url(key):
    s3_client = boto3.client('s3')
    url = s3_client.generate_presigned_url(
            ClientMethod = 'get_object',
            Params = {'Bucket' : AWS_S3_BUCKET_NAME, 'Key' : key},
            ExpiresIn = 259200,
            HttpMethod = 'GET')
    return url


def my_s3_link_url(key):
    url = 'https://s3-ap-northeast-1.amazonaws.com/' + key
    return url


def exist_key_s3(key):
    s3 = boto3.resource('s3')
    bucket = s3.Bucket(AWS_S3_BUCKET_NAME)
    
    try:
        bucket.Object(key).load()
    except:
        return False
    else:
        return True


def download_from_s3(key):

    s3 = boto3.resource('s3')
    bucket = s3.Bucket(AWS_S3_BUCKET_NAME)

    download_path = os.path.join(static_tmp_path,os.path.basename(key))

    bucket.download_file(key, download_path)

    return download_path


def upload_to_s3(source_path, key):
    
    s3 = boto3.resource('s3')
    bucket = s3.Bucket(AWS_S3_BUCKET_NAME)

    bucket.upload_file(source_path, key)

    return key


def upload_to_s3_category(source_path, category):

    key = os.path.join(category, os.path.basename(source_path))
    key = upload_to_s3(source_path,key)

    return key


def image_send_messages_s3(category):

    image_url, thumb_url = genelate_image_url_s3(category)

    message = [ImageSendMessage(
        original_content_url=image_url,
        preview_image_url=thumb_url
    )]

    return message


def shrink_image(source_path,save_path, target_width, target_height):
    img = Image.open(source_path)
    w, h = img.size

    convert_image = {
        # そのまま
        1: lambda img: img,
        # 左右反転
        2: lambda img: img.transpose(Image.FLIP_LEFT_RIGHT),
        # 180度回転
        3: lambda img: img.transpose(Image.ROTATE_180),
        # 上下反転
        4: lambda img: img.transpose(Image.FLIP_TOP_BOTTOM),
        # 左右反転＆反時計回りに90度回転
        5: lambda img: img.transpose(Image.FLIP_LEFT_RIGHT).transpose(Image.ROTATE_90),
        # 反時計回りに270度回転
        6: lambda img: img.transpose(Image.ROTATE_270),
        # 左右反転＆反時計回りに270度回転
        7: lambda img: img.transpose(Image.FLIP_LEFT_RIGHT).transpose(Image.ROTATE_270), 
        # 反時計回りに90度回転
        8: lambda img: img.transpose(Image.ROTATE_90),
    }

    if target_width < w or target_height < h:
        img.thumbnail((target_width, target_height), Image.ANTIALIAS)

    try:
        exif = img._getexif()
        if exif:
            orientation = exif.get(0x112, 1)
            img = convert_image[orientation](img)
    except:
        print('[Except Log] def=shrink_image exif = img._getexif()')

    img.save(save_path)
    return save_path


def create_s3_thumb(image_key):
    thumb_key = os.path.join('thumb', image_key)
    thumb_path = download_from_s3(image_key)
    thumb_path = shrink_image(thumb_path, thumb_path, 240, 240)
    thumb_key = upload_to_s3(thumb_path, thumb_key)

    return thumb_key


def update_s3_thumb_bach(prefix):
    s3 = boto3.resource('s3')
    bucket = s3.Bucket(AWS_S3_BUCKET_NAME)

    obj_collections = bucket.objects.filter(Prefix=prefix)
    keys = [obj_summary.key for obj_summary in obj_collections if obj_summary.key.endswith('.jpg')]

    for image_key in keys:
        thumb_key = os.path.join('thumb', image_key)

    #サムネイルが無ければ作成
    if not exist_key_s3(thumb_key):
        thumb_key = create_s3_thumb(image_key)

        print('[Image Log] update_s3_thumb'
            + ' create'
            + ' image_key=' + image_key
            + ' thumb_key=' + thumb_key
        )
        
    else:
        print('[Image Log] update_s3_thumb'
            + ' exist'
            + ' image_key=' + image_key
            + ' thumb_key=' + thumb_key
        )


def get_message_pattern(text):
    if text in{'くーちゃん', 'クーちゃん', 'クーチャン', 'ｸｰﾁｬﾝ', 'くー', 'クー', 'ｸｰ'}:
        return 'neko_quu'

    elif text in{'ちょこ', 'チョコ', 'ﾁｮｺ'}:
        return 'neko_choco'

    elif text in{
        '漫画太郎', '漫☆画太郎',
        'みっちー', 'ミッチー',
        'みっちーさん', 'ミッチーサン',
    }:
        return 'gatarou'

    elif text in{'おわかりいただけただろうか'}:
        return 'ghost'

    elif text in{'てすと', 'テスト', 'test'}:
        return 'test'


def get_img_dir(message_pattern):
    if message_pattern in{
        'neko_quu'
    }:
        return 'static/quuimg'

    elif message_pattern in{
        'neko_choco'
    }:
        return 'static/chocoimg'

    elif message_pattern in{
        'test'
    }:
        return 'static/nekoimg'

    else:
        return 'static/specialimg'


def image_send_message_dir(img_dir):
    image_name = random.choice([os.path.basename(f) for f in (
        glob.glob(os.path.join(img_dir, '*.jpg')))])
    image_url = os.path.join(AP_URL, img_dir, image_name)
    image_thumb_url = os.path.join(AP_URL, img_dir, 'thumb', image_name)

    message = ImageSendMessage(
        original_content_url=image_url,
        preview_image_url=image_thumb_url
    )
    print('[Image Log] image_send_message_dir image_url=' + image_url)
    return message


def image_send_message_list(img_dir, img_list):
    image_name = random.choice(img_list)
    image_url = os.path.join(AP_URL, img_dir, image_name)
    image_thumb_url = os.path.join(AP_URL, img_dir, 'thumb', image_name)

    message = ImageSendMessage(
        original_content_url=image_url,
        preview_image_url=image_thumb_url
    )
    print('[Image Log] image_send_message_list image_url=' + image_url)
    return message


def restaurant_image_url(restaurant):
    image_name = restaurant + '.jpg'
    image_url = os.path.join(AP_URL, 'static/restaurantimg', image_name)

    print('[Debug] restaurant_image_url:' + image_url)
    return image_url


def warning_message_text():
    text = random.choice([
        '[警告] コマンドを拒否', '[警告] 危険なコマンド', '[警告] 禁止されています', '[警告] アクセスできません',
        'やめろ', 'こら', '危険', '😾', 'あぶない',
        '[?ｭｦ???] ??ｳ?????ｳ???????????ｦ', '[隴ｦ蜻馨 繧ｳ繝槭Φ繝峨ｒ諡貞凄'
    ])
    return text


def restaurant_message_text():
    text = random.choice([
        '猫', 'ねこ', 'ネコ', 'cat', 'neko', 'ひめ','ちゅーる'
    ])
    return text


def get_line_id(event):
    """
    LINEに関するIDを取得する

    Parameters
    ----------
    event : Event Object
    LINEのイベントオブジェクト

    Returns
    -------
    user_name : str
    user_id : str
    group_id : str
    room_id : str

    """

    try:
        if isinstance(event.source, SourceUser):
            profile = line_bot_api.get_profile(event.source.user_id)

            user_name = profile.display_name
            user_id = event.source.user_id
            group_id = ''
            room_id = ''

        elif isinstance(event.source, SourceGroup):
            profile = line_bot_api.get_group_member_profile(
                event.source.group_id, event.source.user_id)

            user_name = profile.display_name
            user_id = event.source.user_id
            group_id = event.source.group_id
            room_id = ''

        elif isinstance(event.source, SourceRoom):
            profile = line_bot_api.get_room_member_profile(
                event.source.room_id, event.source.user_id)

            user_name = profile.display_name
            user_id = event.source.user_id
            group_id = ''
            room_id = event.source.room_id

    except:
        user_name = 'Unknown'
        user_id = ''
        group_id = ''
        room_id = ''

    return user_name, user_id, group_id, room_id

@app.route('/')
def hello_world():
    return 'にゃー'


@app.route('/callback', methods=['POST'])
def callback():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)
    #app.logger.info('Request body: ' + body)

    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'


@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):

    epsilon = 0.05
    text = event.message.text
    textn = my_normalize(text)

    intent = Intent(textn).check_intent(False)
    entity_exact = Entity(textn).check_entity(True)
    entity_partial = Entity(textn).check_entity(False)
    setting = Setting()
    
    #古い判定
    message_pattern = get_message_pattern(textn)
    img_dir = get_img_dir(message_pattern)

    user_name, user_id, group_id, room_id = get_line_id(event)
    print('[Event Log]'
        + ' text_message'
        + ' user_name=' + str(user_name)
        + ' user_id=' + str(user_id)
        + ' group_id=' + str(group_id)
        + ' room_id=' + str(room_id)
        + ' text=' + str(text)
        + ' textn=' + str(textn)
        + ' intent.name=' + str(intent.name)
        + ' entity_exact.name=' + str(entity_exact.name)
        + ' entity_partial.name=' + str(entity_partial.name)
    )

    send_text = ''

    #Entity完全一致の判定
    if entity_exact.match:
        
        # スペシャル判定
        if entity_exact.name in {
            '@foo',
        }:

            # line_bot_api.reply_message(
            #     event.reply_token,
            #     [
            #         text_send_messages_db(entity_exact)[0],
            #         image_send_messages_s3(entity_exact.category)
            #     ]
            # )

            return

        #飲みいく判定（食べログカルーセルを表示）
        elif entity_exact.name in {
            '@godrinking'
        }:

            t_select = Tabelog().select
            t_select.select_tanelog_links()

            if t_select.selected_count > 0:

                template_message = TemplateSendMessage(
                    alt_text='Tabelog Carousel',
                    template=CarouselTemplate(columns=t_select.carousel_columns())
                )

                line_bot_api.reply_message(event.reply_token,
                    [
                        TextSendMessage(text=random.choice(['どこにしよう','かるくで'])),
                        template_message,
                    ]
                )
                return

        # イヌ判定（テシストを返信して退出）
        elif entity_exact.name in{'@dog'}:

            replies = text_send_messages_db(entity_exact, textn)
            line_bot_api.reply_message(event.reply_token, replies)

            if isinstance(event.source, SourceGroup):
                line_bot_api.leave_group(event.source.group_id)
            elif isinstance(event.source, SourceRoom):
                line_bot_api.leave_room(event.source.room_id)

            return

        #ノーマル返信判定（テキストとイメージを返信）
        else:

            replies = text_send_messages_db(entity_exact) + image_send_messages_s3(entity_exact.category)
            line_bot_api.reply_message(event.reply_token,replies)

            return


    #Intent一致の判定
    if intent.match:

        if intent.name == '#change_setting':
            
            if setting.check_admin_line_user(user_id):

                if entity_partial.match:
                    if entity_partial.position < intent.position:
                    
                        if entity_partial.name == '@access_management':

                            if setting.enable_access_management == 'True':
                                setting = setting.update_enable_access_management('False')
                                send_text = 'にゃー（アクセス管理 オフ）'
                            else:
                                setting = setting.update_enable_access_management('True')
                                send_text = 'にゃー（アクセス管理 オン）'

                        if send_text != '':
                            line_bot_api.reply_message(
                                event.reply_token, TextMessage(text=send_text))

                        return

        elif intent.name == '#change_setting_on':
            
            if setting.check_admin_line_user(user_id):

                if entity_partial.match:
                    if entity_partial.position < intent.position:
                    
                        if entity_partial.name == '@access_management':

                            if setting.enable_access_management == 'True':
                                send_text = 'すでにアクセス管理は有効だよ'
                            else:
                                setting = setting.update_enable_access_management('True')
                                send_text = 'にゃー（アクセス管理 オン）'

                        if send_text != '':
                            line_bot_api.reply_message(
                                event.reply_token, TextMessage(text=send_text))

                        return

        elif intent.name == '#change_setting_off':
            
            if setting.check_admin_line_user(user_id):

                if entity_partial.match:
                    if entity_partial.position < intent.position:
                    
                        if entity_partial.name == '@access_management':

                            if setting.enable_access_management == 'True':
                                setting = setting.update_enable_access_management('False')
                                send_text = 'にゃー（アクセス管理 オフ）'
                            else:
                                send_text = 'すでにアクセス管理は無効だよ'

                            if send_text != '':
                                line_bot_api.reply_message(
                                    event.reply_token, TextMessage(text=send_text))

                            return
                    
                        elif entity_partial.name == '@current_upload_category':
                            if entity_partial.position < intent.position:

                                setting.update_current_upload_category('')
                                send_text = 'にゃー（アップロード機能 オフ）'

                            if send_text != '':
                                line_bot_api.reply_message(
                                    event.reply_token, TextMessage(text=send_text))

                            return

        elif intent.name == '#change_upload_target':

            if setting.check_access_allow(user_id):

                if entity_partial.match:
                    if entity_partial.position < intent.position:

                        if entity_partial.name == '@neko_image':
                            setting.update_current_upload_category('image/neko')
                            send_text = 'ねこ画像を送って'

                        elif entity_partial.name == '@neko_cyu-ru_image':
                            setting.update_current_upload_category('image/neko_cyu-ru')
                            send_text = 'ちゅーる画像を送って'

                        elif entity_partial.name == '@kitada_image':
                            setting.update_current_upload_category('image/kitada')
                            send_text = '北田さん画像を送って'

                        elif entity_partial.name == '@wakamatsu_image':
                            setting.update_current_upload_category('image/gakky')
                            send_text = '若松さん（ガッキー）画像を送って'

                        elif entity_partial.name in {
                            '@tebelog_link', '@tabelog_izakaya',
                        }:
                            setting.update_current_upload_category('tabelog/godrinking')
                            send_text = '食べログのリンク送って'

                        if send_text != '':
                            line_bot_api.reply_message(
                                event.reply_token, TextMessage(text=send_text))

                        return

        elif intent.name == '#check_setting':

            if entity_partial.match:
                if entity_partial.position < intent.position:

                    if entity_partial.name == '@access_management':
                        if setting.enable_access_management == 'True':
                            send_text = 'アクセス管理 オンだよ'
                        else:
                            send_text = 'アクセス管理 オフだよ'

                    elif entity_partial.name == '@current_upload_category':
                        if setting.current_upload_category == '':
                            send_text = 'アップロード機能はオフだよ'
                        else:
                            send_text = '現在のアップロードカテゴリ： ' + setting.current_upload_category

                    if send_text != '':
                        line_bot_api.reply_message(
                            event.reply_token, TextMessage(text=send_text))

                    return

        elif intent.name == '#update':
            
            if entity_partial.match:
                if entity_partial.position < intent.position:

                    if entity_partial.name == '@thumb':
                        if setting.enable_access_management == 'True':

                            send_text = 'サムネイル更新しとく'

                            line_bot_api.reply_message(
                                event.reply_token, TextMessage(text=send_text))

                            update_s3_thumb_bach('nekobot/image/')

                    return

    # test判定
    send_text = ''
    if message_pattern == 'test':

        t_select = Tabelog().select
        t_select.select_tanelog_links()

        if t_select.selected_count > 0:

            template_message = TemplateSendMessage(
                alt_text='Tabelog Carousel',
                template=CarouselTemplate(columns=t_select.carousel_columns())
            )

            line_bot_api.reply_message(event.reply_token,
                [
                    TextSendMessage(text=random.choice(['tabelog test','食べログ テスト'])),
                    template_message,
                ]
            )
            return


    # 古いスペシャル判定
    elif message_pattern == 'ghost':
        if epsilon <= random.random():
            send_text = warning_message_text()
            line_bot_api.reply_message(event.reply_token,TextSendMessage(text=send_text))

        else:
            line_bot_api.reply_message(event.reply_token,
                [
                    TextSendMessage(text=random.choice(
                        ['笞??冗┌蜉ｹ縺ｪ繧ｳ繝槭Φ繝', '縺翫ｏ縺九ｊ縺?◆縺?縺代◆縺?繧阪≧縺'])),
                    image_send_message_list(
                        img_dir, ['IMG_0775.jpg', 'IMG_0847.jpg', 'IMG_0775.jpg', 'IMG_0847.jpg']),
                    TextSendMessage(text='...'),
                    TextSendMessage(text='エラー')
                ]
            )
        return

    elif message_pattern == 'gatarou':
        if epsilon <= random.random():
            send_text = warning_message_text()
            line_bot_api.reply_message(event.reply_token,
                TextSendMessage(text=send_text)
            )

        else:
            line_bot_api.reply_message(event.reply_token,
                [
                    TextSendMessage(text=random.choice(
                        ['??ｷ??｣??ｼ?????ｷ??｣??ｼ?????ｷ??｣??ｼ?????ｷ??｣??ｼ', '･ｷ･罍ｼ｡｡･ｷ･罍ｼ｡｡･ｷ･罍ｼ'])),
                    image_send_message_list(
                        img_dir, ['IMG_0761.jpg', 'IMG_0761_2.jpg', 'IMG_0761.jpg', 'IMG_0761_2.jpg']),
                    TextSendMessage(text='...'),
                    TextSendMessage(text='エラー')
                ]
            )
        return

    #食べログのリンク判定
    if setting.check_access_allow(user_id):
        if setting.current_upload_category == 'tabelog/godrinking':
            
            t_insert = Tabelog().insert
            t_insert.set_target_url(text)

            if t_insert.url_exists():

                send_text = 'もう知ってる'
                line_bot_api.reply_message(
                    event.reply_token,TextSendMessage(text=send_text)
                )

                return

            if t_insert.is_tabelog_domain():

                send_text = '食べログのリンクもらった'
                line_bot_api.reply_message(
                    event.reply_token,TextSendMessage(text=send_text)
                )

                t_insert.insert_tabelog_link()

                return


@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    extension = '.jpg'
    dt_now = datetime.datetime.now()
    str_now = dt_now.strftime('%Y%m%d-%H%M')

    setting = Setting()

    user_name, user_id, group_id, room_id = get_line_id(event)
    print('[Event Log]'
        + ' image_message'
        + ' user_name=' + str(user_name)
        + ' user_id=' + str(user_id)
        + ' group_id=' + str(group_id)
        + ' room_id=' + str(room_id)
        + ' current_upload_category=' + str(setting.current_upload_category)
    )

    if setting.check_access_allow(user_id):
        if setting.current_upload_category.split('/')[0] == 'image':

            message_content = line_bot_api.get_message_content(event.message.id)

            with tempfile.NamedTemporaryFile(dir=static_tmp_path, prefix=str_now+'-', delete=False) as tf:
                for chunk in message_content.iter_content():
                    tf.write(chunk)
                
                tf_path = tf.name

            dist_path = tf_path + extension
            os.rename(tf_path, dist_path)
            
            upload_to_s3_category(dist_path, setting.current_upload_category)
            
            send_text = '画像もらった'
            line_bot_api.reply_message(
                event.reply_token,TextSendMessage(text=send_text)
            )


@handler.add(JoinEvent)
def handle_join(event):
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text='ねこって言ってみ')
    )


if __name__ == "__main__":
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
