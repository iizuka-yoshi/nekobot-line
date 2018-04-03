# -*- coding: utf-8 -*-

#  Licensed under the Apache License, Version 2.0 (the "License"); you may
#  not use this file except in compliance with the License. You may obtain
#  a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
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

static_tmp_path = "https://line-bot-sdk-python-test.herokuapp.com/static/tmp"
static_nekoimg_path = "https://line-bot-sdk-python-test.herokuapp.com/static/nekoimg"
static_specialimg_path = "https://line-bot-sdk-python-test.herokuapp.com/static/specialimg"

# function for create tmp dir for download content
def make_static_tmp_dir():
    try:
        os.makedirs(static_tmp_path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(static_tmp_path):
            pass
        else:
            raise

def make_image_send_message():
    image_name = random.choice(os.listdir("static/nekoimg"))
    image_url = os.path.join(static_nekoimg_path ,image_name)
    image_thumb_url = os.path.join(static_nekoimg_path ,"thumb",image_name)

    message = ImageSendMessage(
        original_content_url=image_url,
        preview_image_url=image_thumb_url
    )
    
    return message

def make_image_send_message_micchi():
    image_name = 'IMG_0761.jpg'
    image_url = os.path.join(static_specialimg_path ,image_name)
    image_thumb_url = os.path.join(static_specialimg_path ,"thumb",image_name)
    
    message = ImageSendMessage(
        original_content_url=image_url,
        preview_image_url=image_thumb_url
    )
    return message

def make_image_send_message_kitada():
    image_name = 'IMG_3624.jpg'
    image_url = os.path.join(static_specialimg_path ,image_name)
    image_thumb_url = os.path.join(static_specialimg_path ,"thumb",image_name)
    
    message = ImageSendMessage(
       original_content_url=image_url,
       preview_image_url=image_thumb_url
    )
    return message

@app.route("/")
def hello_world():
    return "hello world!"


@app.route("/callback", methods=['POST'])
def callback():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'


@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    text = event.message.text
    text = text.replace(' ','')
    text = text.replace('　','')
    text = text.strip()
    text = text.lower()
    
    if text == "いぬ" or text == "イヌ" or text == "犬" or text == "dog":
        line_bot_api.reply_message(
            event.reply_token, TextMessage(text=event.message.text + "きらい"))
            
        if isinstance(event.source, SourceGroup):
            line_bot_api.leave_group(event.source.group_id)
        elif isinstance(event.source, SourceRoom):
            line_bot_api.leave_room(event.source.room_id)

    elif text == "みっちー" or text == "ミッチー" or text == "漫画太郎" or text == "漫☆画太郎":
        line_bot_api.reply_message(event.reply_token,
           [
                make_image_send_message_micchi(),
                TextSendMessage(text="シャー")
            ]
        )
        
        if isinstance(event.source, SourceGroup):
            line_bot_api.leave_group(event.source.group_id)
        elif isinstance(event.source, SourceRoom):
            line_bot_api.leave_room(event.source.room_id)

    elif text == "kitada" or text == "北田" or text == "きただ" or text == "キタダ" or text == "北田さん" or text == "きたださん" or text == "キタダサン":
        line_bot_api.reply_message(event.reply_token,
            make_image_send_message_kitada()
       )

    elif text == "猫" or text == "寝子" or text == "姫":
        line_bot_api.reply_message(event.reply_token,
           [
                TextSendMessage(text="Zzz..."),
                make_image_send_message()
            ]
        )

    elif text == "ねこ" or text == "ひめ":
        line_bot_api.reply_message(event.reply_token,
            [
                TextSendMessage(text="にゃー"),
                make_image_send_message()
             ]
        )

    elif text == "ネコ" or text == "ヒメ":
        line_bot_api.reply_message(event.reply_token,
            [
                TextSendMessage(text="ニャー"),
                make_image_send_message()
             ]
        )

    elif text == "cat" or text == "neko":
        line_bot_api.reply_message(event.reply_token,
            [
                TextSendMessage(text="nya-"),
                make_image_send_message()
            ]
        )

    elif text == "test":

        line_bot_api.reply_message(event.reply_token,
            [
                TextSendMessage(text="test"),
                TextSendMessage(text=os.path.join(static_nekoimg_path,"IMG_2992.jpg")),
                TextSendMessage(text=os.path.join(static_nekoimg_path,"thumb","IMG_2992-thumb.jpg"))
            ])

@handler.add(JoinEvent)
def handle_join(event):
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="ねこって言ってみ"))

if __name__ == "__main__":
    # create tmp dir for download content
    make_static_tmp_dir()
    
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
