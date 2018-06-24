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

from PIL import Image

from argparse import ArgumentParser

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

USER_ID_IIZUKA = 'U35bca0dfb497d294737b7b25f4261a0b'

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
                'WHERE entity = %s ;'
        
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

    def update_enable_access_management(self,value):
        with psycopg2.connect(DB_URL) as conn:
            with conn.cursor() as curs:

                curs.execute(self._sql_update, (value, 'enable_access_management',))
                conn.commit()

        self.enable_access_management = self._get_enable_access_management()

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


def text_send_messages_db(entity):
    
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
        messages.append(ImageSendMessage(text=reply_text))

    return messages


def get_s3_image_prefix(img_category):
    prefix = img_category
    return prefix

def upload_image_to_s3(source_image_path, img_category):

    prefix = get_s3_image_prefix(img_category)

    image_key = os.path.join(prefix, os.path.basename(source_image_path))
    
    s3 = boto3.resource('s3')
    bucket = s3.Bucket(AWS_S3_BUCKET_NAME)
    bucket.upload_file(source_image_path, image_key)

    return image_key

def download_image_from_s3(img_category):

    prefix = get_s3_image_prefix(img_category)

    s3 = boto3.resource('s3')
    bucket = s3.Bucket(AWS_S3_BUCKET_NAME)

    obj_collection = bucket.objects.filter(Prefix=prefix)
    keys = [obj_summary.key for obj_summary in obj_collection]

    image_key = random.choice(keys)
    download_path = os.path.join(static_tmp_path,os.path.basename(image_key))

    bucket.download_file(image_key, download_path)

    return download_path


def image_send_message_s3(img_category):

    image_path = download_image_from_s3(img_category)
    image_name = os.path.basename(image_path)
    image_dir = os.path.dirname(image_path)
    thumb_path = os.path.join(image_dir, 'thumb', image_name)

    shrink_image(image_path,thumb_path,240,240)

    image_url = os.path.join(AP_URL, 'static','tmp', image_name)
    image_thumb_url = os.path.join(AP_URL, 'static', 'tmp', 'thumb', image_name)

    message = ImageSendMessage(
        original_content_url=image_url,
        preview_image_url=image_thumb_url
    )
    print('[Image Log] image_send_message_s3 image_url=' + image_url)
    return message


def shrink_image(source_path,save_path, target_width, target_height):
    img = Image.open(source_path)
    w, h = img.size

    if target_width < w or target_height < h:
        img.thumbnail((target_width,target_height),Image.ANTIALIAS)
        img.save(save_path)
    
    return save_path


def get_message_pattern(text):
    text = text.replace(' ', '')
    text = text.replace('　', '')
    text = text.replace('〜', 'ー')
    text = text.replace('！', '')
    text = text.replace('？', '')
    text = text.replace('!', '')
    text = text.replace('?', '')
    text = text.replace('、', '')
    text = text.replace('。', '')
    text = text.strip()
    text = text.lower()

    if text in{'ひめ', 'ヒメ', 'ﾋﾒ', '姫', 'hime', 'ひめちゃん', 'ヒメちゃん', 'ヒメチャン'}:
        return 'neko_hime'

    elif text in{'くーちゃん', 'クーちゃん', 'クーチャン', 'ｸｰﾁｬﾝ', 'くー', 'クー', 'ｸｰ'}:
        return 'neko_quu'

    elif text in{'ちょこ', 'チョコ', 'ﾁｮｺ'}:
        return 'neko_choco'

    elif text in{'ねこ', 'ねこちゃん', 'にゃんこ'}:
        return 'neko_hiragana'

    elif text in{'猫', '寝子', '猫ちゃん'}:
        return 'neko_kanji'

    elif text in{'ネコ', 'ネコちゃん', 'ネコチャン', 'キティ', 'キティちゃん'}:
        return 'neko_kana_full'

    elif text in{'ﾈｺ', 'ﾈｺﾁｬﾝ'}:
        return 'neko_kana_half'

    elif text in{'ｎｅｋｏ', 'ｎｅｃｏ'}:
        return 'neko_roma_full'

    elif text in{'neko', 'neco'}:
        return 'neko_roma_half'

    elif text in{'ｃａｔ'}:
        return 'neko_eng_full'

    elif text in{'cat', 'cats', 'kitty'}:
        return 'neko_eng_half'

    elif text in{'🐈', '🐱', '😸', '😹', '😺', '😻', '😼', '😽', '😾', '😿', '🙀'}:
        return 'neko_emoji'

    elif text in{
        'チャオちゅーる', 'ちゃおちゅーる', 'チャオチュール', 'ciaoチュール',
        'ちゅーる', 'チュール',
        'いなば食品', 'いなば', 'イナバ', 'inaba',
            'おやつ', 'オヤツ'}:
        return 'neko_cyu-ru'

    elif text in{
        '犬', 'いぬ', 'イヌ', 'ｲﾇ', 'わんちゃん', 'ワンちゃん', 'ワンチャン', 'ﾜﾝﾁｬﾝ',
        'ｄｏｇ', 'dog',
        '🐕', '🐩', '🐶'
    }:
        return 'dog'

    elif text in{
        '北田', 'きただ', 'キタダ', 'ｷﾀﾀﾞﾞ', 'ｋｉｔａｄａ', 'kitada',
        '北田さん', 'きたださん', 'キタダサン', 'ｷﾀﾀﾞｻﾝ',
        '北', 'きた', 'キタ', 'ｷﾀ', 'ｋｉｔａ', 'kita'
    }:
        return 'kitada'

    elif text in{
        '若松', 'わかまつ', 'ワカマツ', 'ﾜｶﾏﾂ',
        '若松さん', 'わかまつさん', 'ワカマツサン', 'ﾜｶﾏﾂｻﾝ',
        'ｗａｋａｍａｔｓｕ', 'wakamatsu',
        '若', 'わか', 'ワカ', 'ﾜｶ', 'ｗａｋａ', 'waka',
        '若さま', 'わかさま', 'ワカサマ', 'ﾜｶｻﾏ', 'wakasama',
        'トリミングおじさん', 'トリミング', 'トリマー'
    }:
        return 'wakamatsu'

    elif text in{
        'あご', 'アゴ', 'ｱｺﾞ', 'あご松', 'あごまつ', 'アゴマツ', 'ｱｺﾞﾏﾂ',
        'ａｇｏ', 'ago'
    }:
        return 'ago'

    elif text in{
        '米田', 'よねだ', 'ヨネダ', 'ﾖﾈﾀﾞ',
        '米田さん', 'よねださん', 'ヨネダサン', 'ﾖﾈﾀﾞｻﾝ',
        'ｙｏｎｅｄａ', 'yoneda',
        '米', 'よね', 'ヨネ', 'ﾖﾈ', 'ｙｏｎｅ', 'yone',
        '米さま', 'よねさま', 'ヨネサマ', 'ﾖﾈｻﾏ', 'ｙｏｎｅｓａｍａ', 'yonesama',
        '米さん', 'よねさん', 'ヨネサン', 'ﾖﾈｻﾝ', 'ｙｏｎｅｓａｎ', 'yonesan'
    }:
        return 'yoneda'

    elif text in{
        '漫画太郎', '漫☆画太郎',
        'みっちー', 'ミッチー',
        'みっちーさん', 'ミッチーサン',
    }:
        return 'gatarou'

    elif text in{'おわかりいただけただろうか'}:
        return 'ghost'

    elif text in{'きむたく', 'キムタク', 'ｷﾑﾀｸ', 'ｋｉｍｕｔａｋｕ', 'kimutaku'}:
        return 'kimutaku'

    elif text in{'竹内涼真', '涼真', 'りょうま', 'りょーま', 'リョウマ', 'リョーマ'}:
        return 'ryoma'

    elif text in{
        '新田真剣佑', '真剣佑', '前田真剣佑',
        'あらたまっけんゆう', 'まっけんゆう', 'まえだまっけんゆう',
        'アラタマッケンユウ', 'マッケンユウ', 'マエダマッケンユウ',
        'まっけん', 'マッケン'
    }:
        return 'makken'

    elif text in{
        'お疲れ様です', 'お疲れさまです', 'おつかれさまです', 'オツカレサマデス',
        'お疲れ様', 'お疲れさま', 'おつかれさま', 'オツカレサマ',
        'お疲れ', 'おつかれ', 'オツカレ',
        'お疲れー', 'おつかれー', 'オツカレー',
        '乙', 'おつ', 'オツ',
        '乙ー', 'おつー', 'オツー',
        'お疲れ様でした', 'お疲れさまでした', 'おつかれさまでした', 'オツカレサマデシタ',
        '疲れた', 'つかれた', 'ツカレタ',
        'ご苦労様', 'ご苦労さま', 'ごくろうさま', 'ゴクロウサマ',
        'ご苦労', 'ごくろう', 'ゴクロウ'
    }:
        return 'goodjob'

    elif text in{
        'carousel',
        '行きますか', 'いきますか', 'イキマスカ',
        '行きます', 'いきます', 'イキマス',
        '行く', 'いく', 'イク',
        'どうしますか', 'ドウシマスカ',
        'どうします', 'ドウシマス',
        'どうする', 'ドウスル',
        '終わった', 'おわった', 'オワッタ',
        '終わる', 'おわる', 'オワル',
        'そろそろ', 'ソロソロ',
        '飲み', 'のみ', 'ノミ',
        '飲み会', 'のみかい', 'ノミカイ',
        '飲み行きますか', '飲みいきますか', 'のみいきますか', 'ノミイキマスカ',
        '飲み行きます', '飲みいきます', 'のみいきます', 'ノミイキマス',
        '飲み行く', '飲みいく', 'のみいく', 'ノミイク',
    }:
        return 'carousel'

    elif text in{'てすと', 'テスト', 'ﾃｽﾄ', 'test'}:
        return 'test1'

    elif text in{'db'}:
        return 'test2'


def get_img_dir(message_pattern):
    if message_pattern in{
        'neko_hime', 'neko_hiragana', 'neko_kanji', 'neko_kana_full', 'neko_kana_half',
        'neko_roma_full', 'neko_roma_half', 'neko_eng_full', 'neko_eng_half', 'neko_emoji'
    }:
        return 'static/nekoimg'

    elif message_pattern in{
        'cyu-ru'
    }:
        return 'static/cyu-ruimg'

    elif message_pattern in{
        'neko_quu'
    }:
        return 'static/quuimg'

    elif message_pattern in{
        'neko_choco'
    }:
        return 'static/chocoimg'

    elif message_pattern in{
        'kitada'
    }:
        return 'static/kitadaimg'

    elif message_pattern in{
        'ago'
    }:
        return 'static/wakamatsuimg'

    elif message_pattern in{
        'wakamatsu'
    }:
        return 'static/gakkiimg'

    elif message_pattern in{
        'yoneda'
    }:
        return 'static/yonedaimg'

    elif message_pattern in{
        'kimutaku'
    }:
        return 'static/kimutakuimg'

    elif message_pattern in{
        'ryoma'
    }:
        return 'static/ryomaimg'

    elif message_pattern in{
        'makken'
    }:
        return 'static/makkenimg'

    elif message_pattern in{
        'goodjob'
    }:
        return 'static/goodjobimg'

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
    print('[Image Log] image_url=' + image_url)
    return message


def image_send_message_list(img_dir, img_list):
    image_name = random.choice(img_list)
    image_url = os.path.join(AP_URL, img_dir, image_name)
    image_thumb_url = os.path.join(AP_URL, img_dir, 'thumb', image_name)

    message = ImageSendMessage(
        original_content_url=image_url,
        preview_image_url=image_thumb_url
    )
    print('[Image Log] image_url=' + image_url)
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
        '猫', 'ねこ', 'ネコ', 'cat', 'neko', 'ﾈｺﾁｬﾝ', 'ひめ',
    ])
    return text


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
    textn = neologdn.normalize(text)
    textn = textn.lower()

    intent = Intent(textn).check_intent(False)
    entity_exact = Entity(textn).check_entity(True)
    entity_partial = Entity(textn).check_entity(False)
    setting = Setting()
    
    #古い判定
    message_pattern = get_message_pattern(textn)
    img_dir = get_img_dir(message_pattern)

    # log
    try:
        if isinstance(event.source, SourceUser):
            profile = line_bot_api.get_profile(event.source.user_id)
            user_id = profile.user_id
            user_name = profile.display_name

        elif isinstance(event.source, SourceGroup):
            profile = line_bot_api.get_group_member_profile(
                event.source.group_id, event.source.user_id)
            user_id = profile.user_id
            user_name = profile.display_name

        elif isinstance(event.source, SourceRoom):
            profile = line_bot_api.get_room_member_profile(
                event.source.room_id, event.source.user_id)
            user_id = profile.user_id
            user_name = profile.display_name

    except:
        user_id = 'Unknown'
        user_name = 'Unknown'

    print('[Event Log]'
        + ' text_message'
        + ' user_id=' + str(user_id)
        + ' user_name=' + str(user_name)
        + ' text=' + str(text)
        + ' message_pattern=' + str(message_pattern)
    )

    send_text = ''

    #Entity完全一致の判定
    if entity_exact.match:
        
        # ねこ判定（テキストとイメージを返信）
        if entity_exact.name in {
            'neko_hime', 'neko_hiragana', 'neko_kanji', 'neko_kana',
            'neko_roma', 'neko_eng', 'neko_emoji',
        }:

            line_bot_api.reply_message(
                event.reply_token,
                [
                    text_send_messages_db(entity_exact)[0],
                    image_send_message_s3(entity_exact.category)
                ]
            )

            return

        # イヌ判定（テシストを返信して退出）
        if entity_exact.name in{'dog'}:

            line_bot_api.reply_message(
                event.reply_token, text_send_messages_db(entity_exact)[0]
            )

            if isinstance(event.source, SourceGroup):
                line_bot_api.leave_group(event.source.group_id)
            elif isinstance(event.source, SourceRoom):
                line_bot_api.leave_room(event.source.room_id)

            return

    #Intent一致の判定
    if intent.match:

        if intent.name == 'change_setting':
            
            if setting.check_admin_line_user(user_id):

                #Entity部分一致の判定
                if entity_partial.match:
                    
                    if entity_partial.name == 'access_management':

                        if entity_partial.position < intent.position:

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


    # test判定
    send_text = ''
    if message_pattern == 'test1':
        send_text = 'Amazon S3 から画像を取得します'

    # if send_text != '':
    #     image_name = random.choice(os.listdir(img_dir))
    #     image_url = os.path.join(AP_URL, img_dir, image_name)
    #     image_thumb_url = os.path.join(AP_URL, img_dir, 'thumb', image_name)
    #     line_bot_api.reply_message(event.reply_token,
    #         [
    #             # TextSendMessage(text=send_text),
    #             # TextSendMessage(text=image_url),
    #             # TextSendMessage(text=image_thumb_url),
    #             TextSendMessage(
    #                 text='random test [0-1]'),
    #             TextSendMessage(
    #                 text=str(random.random())),
    #             TextSendMessage(
    #                 text='choice test [0-9]'),
    #             TextSendMessage(text=random.choice(
    #                 ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']))
    #         ]
    #     )

        line_bot_api.reply_message(event.reply_token,
                                   [
                                       TextSendMessage(text=send_text),
                                       image_send_message_s3('')
                                   ]
                                   )


    # スペシャル判定（テキストとイメージを返信。場合によって退出）
    send_text = ''

    if message_pattern == 'cyu-ru':
        send_text = 'ぺろぺろ'
        line_bot_api.reply_message(event.reply_token,
                                   [
                                       TextSendMessage(text=send_text),
                                       image_send_message_dir(img_dir)
                                   ]
                                   )

    if message_pattern == 'kitada':
        line_bot_api.reply_message(event.reply_token,
                                   image_send_message_dir(img_dir)
                                   )

    elif message_pattern == 'wakamatsu':
        line_bot_api.reply_message(event.reply_token,
                                   image_send_message_dir(img_dir)
                                   )

    elif message_pattern == 'ago':
        send_text = 'こら'
        line_bot_api.reply_message(event.reply_token,
                                   [
                                       TextSendMessage(text=send_text),
                                       image_send_message_dir(img_dir)
                                   ]
                                   )

    elif message_pattern == 'yoneda':
        line_bot_api.reply_message(event.reply_token,
                                   image_send_message_dir(img_dir)
                                   )

    elif message_pattern == 'kimutaku':
        send_text = 'まてよ'
        line_bot_api.reply_message(event.reply_token,
                                   [
                                       TextSendMessage(text=send_text),
                                       image_send_message_dir(img_dir)
                                   ]
                                   )

    elif message_pattern == 'ryoma':
        send_text = 'あいしてる'
        line_bot_api.reply_message(event.reply_token,
                                   [
                                       TextSendMessage(text=send_text),
                                       image_send_message_dir(img_dir)
                                   ]
                                   )

    elif message_pattern == 'makken':
        send_text = 'おまえのこと好きと言ってなかったな'
        line_bot_api.reply_message(event.reply_token,
                                   [
                                       TextSendMessage(text=send_text),
                                       image_send_message_dir(img_dir)
                                   ]
                                   )

    elif message_pattern == 'goodjob':
        send_text = 'おつかれさま'
        line_bot_api.reply_message(event.reply_token,
                                   [
                                       TextSendMessage(text=send_text),
                                       image_send_message_dir(img_dir)
                                   ]
                                   )

    elif message_pattern == 'ghost':
        if epsilon <= random.random():
            send_text = warning_message_text()
            line_bot_api.reply_message(event.reply_token,
                                       TextSendMessage(text=send_text)
                                       )

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

    elif message_pattern == 'carousel':
        carousel_template = CarouselTemplate(columns=[
            CarouselColumn(
                thumbnail_image_url=restaurant_image_url('zoot'),
                text='ラーメン、居酒屋、焼きとん\n'+'営業時間:17:00～24:00',
                title='ZOOT [浜松町]',
                actions=[
                    URITemplateAction(
                        label='食べログを見る', uri='https://tabelog.com/tokyo/A1314/A131401/13058997/'),
                    MessageTemplateAction(
                        label='ここにする！', text='ここで！\n'+'https://tabelog.com/tokyo/A1314/A131401/13058997/'),
                    MessageTemplateAction(
                        label='ねこ', text=restaurant_message_text()),
                ]),

            CarouselColumn(
                thumbnail_image_url=restaurant_image_url('seiren'),
                text='中華料理、中国鍋・火鍋、ラーメン\n'+'営業時間:17:00～23:00(L.O. 22:30)',
                title='青蓮 [浜松町]',
                actions=[
                    URITemplateAction(
                        label='食べログを見る', uri='https://tabelog.com/tokyo/A1314/A131401/13109938/'),
                    MessageTemplateAction(
                        label='ここにする！', text='ここで！\n'+'https://tabelog.com/tokyo/A1314/A131401/13109938/'),
                    MessageTemplateAction(
                        label='ねこ', text=restaurant_message_text()),
                ]),

            CarouselColumn(
                thumbnail_image_url=restaurant_image_url('uokin'),
                text='魚介料理・海鮮料理、居酒屋\n'+'営業時間:17:00～23:30',
                title='魚金 [浜松町]',
                actions=[
                    URITemplateAction(
                        label='食べログを見る', uri='https://tabelog.com/tokyo/A1314/A131401/13052364/'),
                    MessageTemplateAction(
                        label='ここにする！', text='ここで！\n'+'https://tabelog.com/tokyo/A1314/A131401/13052364/'),
                    MessageTemplateAction(
                        label='ねこ', text=restaurant_message_text()),
                ]),

            CarouselColumn(
                thumbnail_image_url=restaurant_image_url('risuke'),
                text='牛タン、麦とろ、カレーライス\n'+'営業時間:17:30～22:30',
                title='利助 [浜松町]',
                actions=[
                    URITemplateAction(
                        label='食べログを見る', uri='https://tabelog.com/tokyo/A1314/A131401/13014253/'),
                    MessageTemplateAction(
                        label='ここにする！', text='ここで！\n'+'https://tabelog.com/tokyo/A1314/A131401/13014253/'),
                    MessageTemplateAction(
                        label='ねこ', text=restaurant_message_text()),
                ]),

            CarouselColumn(
                thumbnail_image_url=restaurant_image_url('bonanza'),
                text='ダイニングバー、ワインバー\n' +
                '営業時間:17:00～23:30(L.O.22:30、ドリンクL.O.23:00)',
                title='bonanza [浜松町]',
                actions=[
                    URITemplateAction(
                        label='食べログを見る', uri='https://tabelog.com/tokyo/A1314/A131401/13143248/'),
                    MessageTemplateAction(
                        label='ここにする！', text='ここで！\n'+'https://tabelog.com/tokyo/A1314/A131401/13143248/'),
                    MessageTemplateAction(
                        label='ねこ', text=restaurant_message_text()),
                ]),

            CarouselColumn(
                thumbnail_image_url=restaurant_image_url('tokaihntn'),
                text='王様のブランチ第２位の餃子\n'+'営業時間:17:00～23:00(L.O.22:20)',
                title='東海飯店 [浜松町]',
                actions=[
                    URITemplateAction(
                        label='食べログを見る', uri='https://tabelog.com/tokyo/A1314/A131401/13023334/'),
                    MessageTemplateAction(
                        label='ここにする！', text='ここで！\n'+'https://tabelog.com/tokyo/A1314/A131401/13023334/'),
                    MessageTemplateAction(
                        label='ねこ', text=restaurant_message_text()),
                ]),

            CarouselColumn(
                thumbnail_image_url=restaurant_image_url('settsu'),
                text='居酒屋、インドカレー、和食\n'+'営業時間:14:30〜23:00(L.O.22:15)',
                title='摂津 [浜松町]',
                actions=[
                    URITemplateAction(
                        label='食べログを見る', uri='https://tabelog.com/tokyo/A1314/A131401/13097178/'),
                    MessageTemplateAction(
                        label='ここにする！', text='ここで！\n'+'https://tabelog.com/tokyo/A1314/A131401/13097178/'),
                    MessageTemplateAction(
                        label='ねこ', text=restaurant_message_text()),
                ]),

            CarouselColumn(
                thumbnail_image_url=restaurant_image_url('uma8'),
                text='居酒屋、くじら料理\n'+'営業時間:16:30～23:30',
                title='旨蔵 うま八 [新橋]',
                actions=[
                    URITemplateAction(
                        label='食べログを見る', uri='https://tabelog.com/tokyo/A1301/A130103/13045442/'),
                    MessageTemplateAction(
                        label='ここにする！', text='ここで！\n'+'https://tabelog.com/tokyo/A1301/A130103/13045442/'),
                    MessageTemplateAction(
                        label='ねこ', text=restaurant_message_text()),
                ]),

        ])
        template_message = TemplateSendMessage(
            alt_text='Carousel alt text', template=carousel_template)

        line_bot_api.reply_message(event.reply_token,
                                   [
                                       TextSendMessage(text='どこにしよう'),
                                       template_message,
                                   ]
                                   )

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    extension = '.jpg'
    dt_now = datetime.datetime.now()
    str_now = dt_now.strftime('%Y%m%d-%H%M')

    try:
        if isinstance(event.source, SourceUser):
            profile = line_bot_api.get_profile(event.source.user_id)
            user_id = profile.user_id
            user_name = profile.display_name

        elif isinstance(event.source, SourceGroup):
            profile = line_bot_api.get_group_member_profile(
                event.source.group_id, event.source.user_id)
            user_id = profile.user_id
            user_name = profile.display_name

        elif isinstance(event.source, SourceRoom):
            profile = line_bot_api.get_room_member_profile(
                event.source.room_id, event.source.user_id)
            user_id = profile.user_id
            user_name = profile.display_name

    except:
        user_id = 'Unknown'
        user_name = 'Unknown'

    print('[Event Log]'
          + ' image_message'
          + ' user_id=' + str(user_id)
          + ' user_name=' + str(user_name)
          )

    setting = Setting()

    if setting.check_access_allow(user_id):

        message_content = line_bot_api.get_message_content(event.message.id)

        with tempfile.NamedTemporaryFile(dir=static_tmp_path, prefix=str_now+'-', delete=False) as tf:
            for chunk in message_content.iter_content():
                tf.write(chunk)
            
            tf_path = tf.name

        dist_path = tf_path + extension
        os.rename(tf_path, dist_path)
        
        upload_image_to_s3(dist_path, 'image/neko/')
        
        send_text = 'にゃー（画像ゲット）'

        line_bot_api.reply_message(
            event.reply_token,
            [
                TextSendMessage(text=send_text)
            ]
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
