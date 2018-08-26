# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import errno
import os
import datetime
import time
import glob
import sys
import tempfile
import random
import math
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
    LineBotApiError, InvalidSignatureError
)
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    SourceUser, SourceGroup, SourceRoom,
    TemplateSendMessage, ConfirmTemplate, MessageAction,
    ButtonsTemplate, ImageCarouselTemplate, ImageCarouselColumn, URIAction,
    PostbackAction, DatetimePickerAction,
    CameraAction, CameraRollAction, LocationAction,
    CarouselTemplate, CarouselColumn, PostbackEvent,
    StickerMessage, StickerSendMessage, LocationMessage, LocationSendMessage,
    ImageMessage, VideoMessage, AudioMessage, FileMessage,
    UnfollowEvent, FollowEvent, JoinEvent, LeaveEvent, BeaconEvent,
    FlexSendMessage, BubbleContainer, ImageComponent, BoxComponent,
    TextComponent, SpacerComponent, IconComponent, ButtonComponent,
    SeparatorComponent, QuickReply, QuickReplyButton,
    ImageSendMessage
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
            sql = 'SELECT id, name, example, weight, POSITION(example IN %s) \
                    FROM public.intents \
                    WHERE example = %s \
                    ORDER BY weight DESC;'

        else:
            sql = 'SELECT id, name, example, weight, POSITION(example IN %s) \
                    FROM public.intents \
                    WHERE 0 < POSITION(example IN %s) \
                    ORDER BY weight DESC;'

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
            sql = 'SELECT id, name, synonym, weight, POSITION(synonym IN %s) \
                    FROM public.entities \
                    WHERE synonym = %s \
                    ORDER BY weight DESC;'

        else:
            sql = 'SELECT id, name, synonym, weight, POSITION(synonym IN %s) \
                    FROM public.entities \
                    WHERE 0 < POSITION(synonym IN %s) \
                    ORDER BY weight DESC;'

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
        
        sql = 'SELECT name \
                FROM public.categories \
                WHERE entity = %s \
                ORDER BY RANDOM();'
        
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

    _sql_select = 'SELECT value \
                    FROM public.settings \
                    WHERE name = %s;'

    _sql_update = 'UPDATE public.settings \
                    SET value = %s \
                    WHERE name = %s;'

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

    def set_value_tp(self, value_tp):
        self.name = value_tp[0]
        self.image_key = value_tp[1]
        self.url = value_tp[2]
        self.score = value_tp[3]
        self.station = value_tp[4]
        self.genre = value_tp[5]
        self.hours = value_tp[6]
        return self

    def get_value_tp(self):
        return (self.name, self.image_key, self.url, self.score, self.station, self.genre, self.hours)
        
class _Tabelog_Scraping:

    def __init__(self):
        self.value = _Tabelog_Value()
        self.url = ''

    def _normalize_hours(self, hours):
        hoursn = hours
        hoursn = hoursn.replace('～', '-')
        hoursn = hoursn.replace('・','･')
        hoursn = neologdn.normalize(hoursn)
        hoursn = hoursn[:100]
        return hoursn
    
    def tabelog_scraping(self,url):
        html = urllib.request.urlopen(url).read()
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

        self.value.set_value_tp((name, image_key, url, score, station, genre, hours,))

        return self


class _Tabelog_Insert:
    _DOMAIN = ('tabelog.com', 's.tabelog.com')
    _PATH_DIR_LEVEL = 5

    def __init__(self):
        self.value = _Tabelog_Value()
        self.scraping = _Tabelog_Scraping()
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
        
        self.value = self.scraping.tabelog_scraping(self.url).value

        sql = 'INSERT INTO public.tabelog(\
                name, image_key, url, score, station, genre, hours) \
                VALUES (%s, %s, %s, %s, %s, %s, %s);'
                
        with psycopg2.connect(DB_URL) as conn:
            with conn.cursor() as curs:

                curs.execute(sql, self.value.get_value_tp())
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
            self.values.append(_Tabelog_Value().set_value_tp(value))

        return self

    def select_tabelog_entity(self, entity_name):
        sql = 'SELECT name, image_key, url, score, station, genre, hours \
                    FROM public.tabelog \
                    WHERER entity = %s;'

        with psycopg2.connect(DB_URL) as conn:
            with conn.cursor() as curs:

                curs.execute(sql, (entity_name,))
                if 0 < curs.rowcount:
                    value = curs.fetchone()
                else:
                    value = ()

        return value

    def _tabelog_action_text(self):
        text = random.choice(
            ['猫', 'ねこ', 'ネコ', 'cat', 'neko', 'ひめ', 'ちゅーる']
        )
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
                        URIAction(
                            label='食べログを見る', uri=value.url),
                        MessageAction(
                            label='ここにする！', text='ここで！\n' + value.url),
                        MessageAction(
                            label='ねこ', text=self._tabelog_action_text()),
                    ]
                )
            )

        return columns

    def _review_stars_url(self, score):
        gold_star_image_url = my_s3_link_url('nekobot/tabelog/star_image/gold_star_28.png')
        harf_star_image_url = my_s3_link_url('nekobot/tabelog/star_image/half_star_28.png')
        gray_star_image_url = my_s3_link_url('nekobot/tabelog/star_image/gray_star_28.png')

        stars = []
        for i in range(5):
            if (score - i) >= 1:
                stars.append(gold_star_image_url)
            elif (score - i) >= 0.5:
                stars.append(harf_star_image_url)
            else:
                stars.append(gray_star_image_url)

        return stars

    def flex_send_message_entity(self, entity):
        if not entity.match:
            return False

        value = _Tabelog_Value()
        value.set_value_tp(self.select_tabelog_entity(entity.name))
        
        if value.name == '':
            return False

        stars_url = self._review_stars_url(value.score)

        bubble = BubbleContainer(
            hero=ImageComponent(
                url=value.image_key,
                size='full',
                aspect_ratio='20:13',
                aspect_mode='cover',
                action=URIAction(
                    uri=value.url
                )
            ),
            body=BoxComponent(
                layout='vertical',
                contents=[
                    # title
                    TextComponent(text=value.name,
                        weight='bold',
                        size='xl'
                    ),
                    # review
                    BoxComponent(
                        layout='baseline',
                        margin='md',
                        contents=[
                            IconComponent(size='sm', url=stars_url[0]),
                            IconComponent(size='sm', url=stars_url[1]),
                            IconComponent(size='sm', url=stars_url[2]),
                            IconComponent(size='sm', url=stars_url[3]),
                            IconComponent(size='sm', url=stars_url[4]),
                            TextComponent(
                                text='{:.2f}'.format(value.score),
                                size='sm', color='#999999', margin='md',flex=0)
                        ]
                    ),
                    # info
                    BoxComponent(
                        layout='vertical',
                        margin='lg',
                        spacing='sm',
                        contents=[
                            BoxComponent(
                                layout='baseline',
                                spacing='sm',
                                contents=[
                                    TextComponent(
                                        text='Station',
                                        color='#aaaaaa',
                                        size='sm',
                                        flex=1
                                    ),
                                    TextComponent(
                                        text=value.station,
                                        wrap=True,
                                        color='#666666',
                                        size='sm',
                                        flex=5
                                    )
                                ],
                            ),
                            BoxComponent(
                                layout='baseline',
                                spacing='sm',
                                contents=[
                                    TextComponent(
                                        text='Genre',
                                        color='#aaaaaa',
                                        size='sm',
                                        flex=1
                                    ),
                                    TextComponent(
                                        text=value.genre,
                                        wrap=True,
                                        color='#666666',
                                        size='sm',
                                        flex=5,
                                    ),
                                ],
                            ),
                        ],
                    )
                ],
            ),
            footer=BoxComponent(
                layout='vertical',
                spacing='sm',
                contents=[
                    # callAction, separator, websiteAction
                    SpacerComponent(size='sm'),
                    # callAction
                    ButtonComponent(
                        style='link',
                        height='sm',
                        action=URIAction(label='食べログを見る', uri=value.url),
                    ),
                    # separator
                    SeparatorComponent(),
                    # websiteAction
                    ButtonComponent(
                        style='link',
                        height='sm',
                        action=URIAction(label='WEBSITE', uri="https://example.com")
                    )
                ]
            ),
        )

        message = FlexSendMessage(alt_text="tabelog flex", contents=bubble)
        return message

class _Tabelog_Update:
    _SLEEP_SECOND = 3

    def __init__(self):
        self.scraping = _Tabelog_Scraping()

    def _select_all_keys(self):
        sql = 'SELECT id, url \
	           FROM public.tabelog \
               ORDER BY id ASC;'

        with psycopg2.connect(DB_URL) as conn:
            with conn.cursor() as curs:

                curs.execute(sql)
                if 0 < curs.rowcount:
                    keys = curs.fetchall()
                else:
                    keys = []

        return keys

    def update_tabelog_link(self, id, value):
        sql = 'UPDATE public.tabelog \
	            SET name=%s, score=%s, station=%s, genre=%s, hours=%s \
	            WHERE id = %s;'
                
        with psycopg2.connect(DB_URL) as conn:
            with conn.cursor() as curs:

                curs.execute(
                    sql,
                    (value.name, value.score, value.station, value.genre, value.hours, id)
                )
                conn.commit()

        print('[Event Log]'
            + ' update_tabelog_link'
            + ' id=' + str(id)
            + ' values=('
            + str(value.name) + ', '
            + str(value.score) + ', '
            + str(value.station) + ', '
            + str(value.genre) + ', '
            + str(value.hours) + ')'
        )

    def update_link_batch(self):
        print('[Debug] _Tabelog_Update.update_link_batch start')

        update_keys = self._select_all_keys()

        for update_key in update_keys:
            scraping = self.scraping.tabelog_scraping(update_key[1])
            self.update_tabelog_link(update_key[0],scraping.value)
            time.sleep(self._SLEEP_SECOND)

        print('[Debug] _Tabelog_Update.update_link_batch end')
        return


class Tabelog:

    def __init__(self):
        self.insert = _Tabelog_Insert()
        self.select = _Tabelog_Select()
        self.update = _Tabelog_Update()

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
    
    sql = 'SELECT DISTINCT ON (reply_order) text, reply_order \
            FROM public.replies \
            WHERE entity = %s \
            ORDER BY reply_order ASC, RANDOM();'
    
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

def insert_random_values(value, category):

    sql = 'INSERT INTO public.random_values(\
            category, value, timestamp) \
            VALUES(%s, %s, current_timestamp);'
            
    with psycopg2.connect(DB_URL) as conn:
        with conn.cursor() as curs:

            curs.execute(sql, (category,value,))
            conn.commit()

    return

def select_recent_random_values(category,limit):

    sql = 'SELECT value \
            FROM public.random_values \
            WHERE category = %s \
            ORDER BY timestamp DESC \
            LIMIT %s;'

    with psycopg2.connect(DB_URL) as conn:
        with conn.cursor() as curs:

            curs.execute(sql, (category,limit, ))
            if 0 < curs.rowcount:
                values_tp = curs.fetchall()

                values = []
                for value_tp in values_tp:
                    values.append(value_tp[0])

            else:
                values = []

    return values

def same_random_value(current_value, recent_values):

    ret = False

    for recent_value in recent_values:
        if current_value == recent_value:
            ret = True

    return ret


def genelate_image_url_s3(category):

    s3 = boto3.resource('s3')
    bucket = s3.Bucket(AWS_S3_BUCKET_NAME)

    obj_collections = bucket.objects.filter(Prefix=category)
    keys = [obj_summary.key for obj_summary in obj_collections if obj_summary.key.endswith('.jpg')]

    if not keys:
        return '',''

    same_key = True
    counter = 0
    limit = math.floor(len(keys)/2)
    while same_key:
        image_key = random.choice(keys)
        thumb_key = os.path.join('thumb', image_key)
        
        if limit == 0:
            same_key = False

        else:
            recent_keys = select_recent_random_values(category,limit)
            same_key = same_random_value(image_key, recent_keys)
        
        counter += 1

        print('[Debug] counter=' + str(counter)
            + ' limit=' + str(limit)
            + ' image_key=' + str(image_key)
            + ' same_key=' + str(same_key)
        )

        if counter >= 3:
            break

    insert_random_values(image_key, category)

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

    if not image_url:
        message = []
    else:
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
    print('[Debug] update_s3_thumb_bach start')

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

    print('[Debug] update_s3_thumb_bach end')
    return


def get_message_pattern(text):
    if text in{'てすと', 'テスト', 'test'}:
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


def warning_messages():
    warning_entity = Entity
    warning_entity.match = True
    warning_entity.name = '@warning'

    messages = text_send_messages_db(warning_entity)

    return messages


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

    epsilon = 0.1
    text = event.message.text
    textn = my_normalize(text)

    intent = Intent(textn).check_intent(False)
    entity_exact = Entity(textn).check_entity(True)
    entity_partial = Entity(textn).check_entity(False)
    setting = Setting()
    
    #古い判定
    message_pattern = get_message_pattern(textn)

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
            '@gatarou','@ghost',
        }:

            if epsilon <= random.random():
                replies = warning_messages()
                
            else:
                replies = text_send_messages_db(entity_exact)
                replies[1:0] = image_send_messages_s3(entity_exact.category)

            line_bot_api.reply_message(event.reply_token, replies)
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

                replies = text_send_messages_db(entity_exact) + [template_message]
                line_bot_api.reply_message(event.reply_token,replies)

                return

        #tabelogリンク判定
        elif entity_exact.name.startswith('@tabelog_'):

            t_select = Tabelog().select
            flex = t_select.flex_send_message_entity(entity_exact)

            if flex:
                replies = [TextSendMessage(text=random.choice(['おーけー', 'りょうかい'])),flex]
                line_bot_api.reply_message(event.reply_token, replies)
                
                return

        # イヌ判定（テシストを返信して退出）
        elif entity_exact.name in {
            '@dog'
        }:

            replies = text_send_messages_db(entity_exact, textn)
            line_bot_api.reply_message(event.reply_token, replies)

            if isinstance(event.source, SourceGroup):
                line_bot_api.leave_group(event.source.group_id)
            elif isinstance(event.source, SourceRoom):
                line_bot_api.leave_room(event.source.room_id)

            return

        # テキスト返信判定
        elif entity_partial.name in {
            '@nomicomm',
        }:

            replies = text_send_messages_db(entity_exact)
            line_bot_api.reply_message(event.reply_token, replies)
            
            return

        #テキスト＋画像返信判定
        else:
            replies = text_send_messages_db(entity_exact) + image_send_messages_s3(entity_exact.category)
            if replies:
                line_bot_api.reply_message(event.reply_token,replies)
                return

    #Intent一致の判定
    if intent.match:

        if intent.name in {
            '#is_bad','#bad_is',
        }:
        
            if entity_partial.match:

                if entity_partial.name in {
                    '@kitada','@wakamatsu','@yoneda','@ozeki',
                }:
                    send_text = random.choice(['たしかに', '同意', 'そうね'])
                    
                elif entity_partial.name in {
                    '@yoshi'
                }:
                    send_text = random.choice(['それはない'])

                if send_text != '':
                    line_bot_api.reply_message(
                        event.reply_token, TextMessage(text=send_text))

                return

        elif intent.name == '#change_setting':
            
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
                            setting.update_current_upload_category('image/neko/')
                            send_text = 'ねこ画像を送って'

                        elif entity_partial.name == '@neko_cyu-ru_image':
                            setting.update_current_upload_category('image/neko_cyu-ru/')
                            send_text = 'ちゅーる画像を送って'

                        elif entity_partial.name == '@kitada_image':
                            setting.update_current_upload_category('image/kitada/')
                            send_text = '北田さん画像を送って'

                        elif entity_partial.name == '@wakamatsu_image':
                            setting.update_current_upload_category('image/gakky/')
                            send_text = '若松さん（ガッキー）画像を送って'

                        elif entity_partial.name in {
                            '@tebelog_link', '@tabelog_izakaya',
                        }:
                            setting.update_current_upload_category('tabelog/godrinking/')
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

                            update_s3_thumb_bach('image')

                    elif entity_partial.name == '@tebelog_link':
                        if setting.enable_access_management == 'True':

                            send_text = '食べログ更新しとく'
                            line_bot_api.reply_message(
                                event.reply_token, TextMessage(text=send_text))

                            t_update = Tabelog().update
                            t_update.update_link_batch()

                    return


    #Entity部分一致の判定
    if entity_partial.match:
        
        # 飲みニケーション判定
        if entity_partial.name in {
            '@nomicomm',
        }:

            replies = text_send_messages_db(entity_partial)
            line_bot_api.reply_message(event.reply_token,replies)

            return

        #tabelogリンク判定
        elif entity_partial.name.startswith('@tabelog_'):

            t_select = Tabelog().select
            flex = t_select.flex_send_message_entity(entity_partial)

            if flex != False:
                replies = [TextSendMessage(text=random.choice(['おーけー', 'りょうかい'])),flex]
                line_bot_api.reply_message(event.reply_token, replies)
                
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

    #食べログのリンク判定
    if setting.check_access_allow(user_id):
        if setting.current_upload_category == 'tabelog/godrinking/':
            
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

            send_text = '画像もらった'
            line_bot_api.reply_message(
                event.reply_token,TextSendMessage(text=send_text)
            )

            message_content = line_bot_api.get_message_content(event.message.id)

            with tempfile.NamedTemporaryFile(dir=static_tmp_path, prefix=str_now+'-', delete=False) as tf:
                for chunk in message_content.iter_content():
                    tf.write(chunk)
                
                tf_path = tf.name

            dist_path = tf_path + extension
            os.rename(tf_path, dist_path)
            
            image_key = upload_to_s3_category(dist_path, setting.current_upload_category)
            thumb_key = create_s3_thumb(image_key)

            print('[Image Log]'
                    + ' image_message'
                    + ' upload_image'
                    + ' image_key=' + str(image_key)
                    + ' thumb_key=' + str(thumb_key)
            )

            return

@handler.add(JoinEvent)
def handle_join(event):
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text='ねこって言ってみ')
    )


if __name__ == "__main__":
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
