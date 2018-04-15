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
import glob
import sys
import tempfile
import random
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

# get channel_secret and channel_access_token from your environment variable
channel_secret = os.getenv('LINE_CHANNEL_SECRET', None)
channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', None)
if channel_secret is None:
    print('Specify LINE_CHANNEL_SECRET as environment variable.')
    sys.exit(1)
if channel_access_token is None:
    print('Specify LINE_CHANNEL_ACCESS_TOKEN as environment variable.')
    sys.exit(1)

line_bot_api = LineBotApi(channel_access_token)
handler = WebhookHandler(channel_secret)

base_dir = 'https://nekobot-line.herokuapp.com'
static_tmp_path = 'https://nekobot-line.herokuapp.com/static/tmp'

# function for create tmp dir for download content
def make_static_tmp_dir():
    try:
        os.makedirs(static_tmp_path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(static_tmp_path):
            pass
        else:
            raise

def get_message_pattern(text):
    text = text.replace(' ','')
    text = text.replace('　','')
    text = text.strip()
    text = text.lower()

    if text in{'ひめ','ヒメ','ﾋﾒ','姫','hime','ひめちゃん','ヒメちゃん','ヒメチャン'}:
        return 'neko_hime'

    elif text in{'くーちゃん','クーちゃん','クーチャン','ｸｰﾁｬﾝ'}:
        return 'neko_quu'

    elif text in{'ちょこ','チョコ','ﾁｮｺ'}:
        return 'neko_choco'

    elif text in{'ねこ','ねこちゃん'}:
        return 'neko_hiragana'

    elif text in{'猫','寝子','猫ちゃん'}:
        return 'neko_kanji'

    elif text in{'ネコ','ネコちゃん','ネコチャン'}:
        return 'neko_kana_full'

    elif text in{'ﾈｺ','ﾈｺﾁｬﾝ'}:
        return 'neko_kana_half'

    elif text in{'ｎｅｋｏ','ｎｅｃｏ'}:
        return 'neko_roma_full'

    elif text in{'neko','neco'}:
        return 'neko_roma_half'

    elif text in{'ｃａｔ'}:
        return 'neko_eng_full'

    elif text in{'cat'}:
        return 'neko_eng_half'

    elif text in{'犬','いぬ','イヌ','ｲﾇ','わんちゃん','ワンちゃん','ワンチャン','ﾜﾝﾁｬﾝ','ｄｏｇ','dog'}:
        return 'dog'

    elif text in{
        '北田','きただ','キタダ','ｷﾀﾀﾞﾞ','ｋｉｔａｄａ','kitada',
        '北田さん','きたださん','キタダサン','ｷﾀﾀﾞｻﾝ',
        '北','きた','キタ','ｷﾀ','ｋｉｔａ','kita'
        }:
        return 'kitada'

    elif text in{
        '若松','わかまつ','ワカマツ','ﾜｶﾏﾂ',
        '若松さん','わかまつさん','ワカマツサン','ﾜｶﾏﾂｻﾝ',
        'ｗａｋａｍａｔｓｕ','wakamatsu',
        '若','わか','ワカ','ﾜｶ','ｗａｋａ','waka'
        }:
        return 'wakamatsu'

    elif text in{
        '米田','よねだ','ヨネダ','ﾖﾈﾀﾞ',
        '米田さん','よねださん','ヨネダサン','ﾖﾈﾀﾞｻﾝ',
        'ｙｏｎｅｄａ','yoneda',
        '米','よね','ヨネ','ﾖﾈ','ｙｏｎｅ','yone'
        }:
        return 'yoneda'

    elif text in{
        '漫画太郎','','漫☆画太郎',
        'みっちー',"ミッチー"
        'みっちーさん','ミッチーサン',
        }:
        return 'gatarou'

    elif text in{'おわかりいただけただろうか'}:
        return 'ghost'

    elif text in{'てすと','テスト','ﾃｽﾄ','test'}:
        return 'test'

def get_img_dir(message_pattern):
    if message_pattern in{
        'neko_hime','neko_hiragana','neko_kanji','neko_kana_full','neko_kana_half',
        'neko_roma_full','neko_roma_half','neko_eng_full','neko_eng_half'
        }:
        return 'static/nekoimg'

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
        'wakamatsu'
        }:
        return 'static/wakamatsuimg'

    elif message_pattern in{
        'yoneda'
        }:
        return 'static/yonedaimg'

    elif message_pattern in{
        'test'
        }:
        return 'static/nekoimg'

    else:
        return 'static/specialimg'

def image_send_message_dir(img_dir):
    image_name = random.choice(os.listdir(img_dir))
    image_url = os.path.join(base_dir,img_dir,image_name)
    image_thumb_url = os.path.join(base_dir, img_dir,'thumb',image_name)

    message = ImageSendMessage(
        original_content_url=image_url,
        preview_image_url=image_thumb_url
    )
    return message

def image_send_message_list(img_dir,img_list):
    image_name = random.choice(img_list)
    image_url = os.path.join(base_dir,img_dir,image_name)
    image_thumb_url = os.path.join(base_dir, img_dir,'thumb',image_name)

    message = ImageSendMessage(
        original_content_url=image_url,
        preview_image_url=image_thumb_url
    )
    return message

@app.route('/')
def hello_world():
    return random.choice('にゃー','ニャー','nya-')

