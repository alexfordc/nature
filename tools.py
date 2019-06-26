#  -*- coding: utf-8 -*-
import pandas as pd
import time
from datetime import datetime

import smtplib
from email.mime.text import MIMEText


dss = r'../data/'

def send_email(subject, content):
    # 第三方 SMTP 服务
    mail_host = 'smtp.yeah.net'              # 设置服务器
    mail_username = 'chenzhenhu@yeah.net'   # 用户名
    mail_auth_password = "852299"       # 授权密码

    sender = 'chenzhenhu@yeah.net'
    receivers = 'chenzhenhu@yeah.net'         # 一个收件人
    #receivers = '270114497@qq.com, zhenghaishu@126.com' # 多个收件人

    try:
        message = MIMEText(content, 'plain', 'utf-8')
        message['From'] = sender
        message['To'] =  receivers
        message['Subject'] = str(subject)
        #smtpObj = smtplib.SMTP(mail_host, 25)                               # 生成smtpObj对象，使用非SSL协议端口号25
        smtpObj = smtplib.SMTP_SSL(mail_host, 465)                         # 生成smtpObj对象，使用SSL协议端口号465
        smtpObj.login(mail_username, mail_auth_password)                    # 登录邮箱
        # smtpObj.sendmail(sender, receivers, message.as_string())          # 发送给一人
        smtpObj.sendmail(sender, receivers.split(','), message.as_string()) # 发送给多人
        print ("邮件发送成功")
    except smtplib.SMTPException as e:
        print ("Error: 无法发送邮件")
        print(e)

def is_trade_time():
    now = datetime.now()
    today = now.strftime('%Y-%m-%d')
    weekday = int(now.strftime('%w'))
    #print(weekday)
    if 1 <= weekday <= 5:
        t = time.localtime()
        if (t.tm_hour>9 and t.tm_hour<17) or (t.tm_hour==9 and t.tm_min>20) :
            return True
    else:
        return False

def is_price_time():
    now = datetime.now()
    today = now.strftime('%Y-%m-%d')
    weekday = int(now.strftime('%w'))
    #print(weekday)
    if 1 <= weekday <= 5:
        t = time.localtime()
        if (t.tm_hour>9 and t.tm_hour<15) or (t.tm_hour==9 and t.tm_min>31) :
            return True
    else:
        return False

if __name__ == '__main__':
    pass
