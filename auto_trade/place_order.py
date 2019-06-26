
from multiprocessing.connection import Listener
from multiprocessing.connection import Client
import multiprocessing

import pandas as pd
import time
from datetime import datetime

from nature.auto_trade import auto_trade
from nature import to_log

dss = '../../data/'


def send_instruction(ins_dict):
    address = ('localhost', 9002)
    again = True
    while again:
        time.sleep(1)
        try :
            with Client(address, authkey=b'secret password') as conn:
                # to_log('stare send ins: '+str(ins_dict))
                conn.send(ins_dict)
                again = False
        except:
            pass

#20190522&{'ins': 'buy_order', 'portfolio': 'redian', 'code': '002482', 'num': 3700, 'price': 5.4, 'cost': 19980, 'agent': 'pingan', 'name': '广田集团'}
def record_buy_order(ins_dict):
    filename = dss + 'csv/hold.csv'
    df = pd.read_csv(filename, dtype={'code':'str'})

    #获得原来的cash, 并减少cash
    pre_cash_index = df[(df.portfolio=='cash') & (df.agent==ins_dict['agent'])].index.tolist()
    df.loc[pre_cash_index[0],'cost'] -= ins_dict['cost']

    #文件中不需要保存这两个字段
    if 'ins' in ins_dict:
        ins_dict.pop('ins')
    if 'price' in ins_dict:
        ins_dict.pop('price')

    # 增加date
    now = datetime.now()
    today = now.strftime('%Y-%m-%d')
    ins_dict['date'] = today

    #新增一条记录
    df_dict = pd.DataFrame([ins_dict])
    df = df.append(df_dict, sort=False)
    #print(df)

    df = df[['portfolio','code','cost','num','agent','date']]
    df.to_csv(filename,index=False)

#20190522&{'ins': 'sell_order', 'portfolio': 'redian', 'code': '300199', 'num': 1800, 'price': 11.46, 'cost': 20628, 'agent': 'pingan', 'name': '翰宇药业'}
def record_sell_order(ins_dict):
    filename = dss + 'csv/hold.csv'
    df = pd.read_csv(filename, dtype={'code':'str'})

    #获得原来的cash, 并增加cash
    pre_cash_index = df[(df.portfolio=='cash') & (df.agent==ins_dict['agent'])].index.tolist()
    df.loc[pre_cash_index[0],'cost'] += ins_dict['cost']*(1-0.0015)

    #获得原来的stock
    pre_stock_index = df[(df.portfolio==ins_dict['portfolio']) & (df.code==ins_dict['code']) & (df.num==ins_dict['num']) & (df.agent==ins_dict['agent'])].index.tolist()
    pre_row = df.loc[pre_stock_index[0]]

    #更新组合的profit
    profit = ins_dict['cost']*(1-0.0015) - pre_row['cost']
    profit_index = df[(df.portfolio==ins_dict['portfolio']) & (df.code=='profit') & (df.agent==ins_dict['agent'])].index.tolist()
    df.loc[profit_index[0],'cost'] += profit

    #删除原来的记录
    df = df.drop(index=[pre_stock_index[0]])

    #print(df)
    df = df[['portfolio','code','cost','num','agent','date']]
    df.to_csv(filename,index=False)

def record_order(order):
    ins = order['ins']
    if ins == 'buy_order':
        record_buy_order(order)
    if ins == 'sell_order':
        record_sell_order(order)

def append_order(order):
    filename = dss + 'csv/order.csv'
    now = datetime.now()
    today = now.strftime('%Y%m%d')
    order = today + '&' + order + '&n'
    with open(filename, 'a', encoding='utf-8') as f:
        f.write(order+'\n')

#{'ins':'buy_order','portfolio':'original','code':'300408','num':1000,'cost':19999,'price':11.88,'agent':'pingan'}
def place_order(order):
    r = False
    try:
        if order['agent']=='pingan' and order['ins']=='buy_order':
            r = auto_trade.pingan_buy(order['code'],order['price'],order['num'])
        if order['agent']=='pingan' and order['ins']=='sell_order':
            r = auto_trade.pingan_sell(order['code'],order['price'],order['num'])
        if order['agent']=='gtja' and order['ins']=='buy_order':
            r = auto_trade.gtja_buy(order['code'],order['price'],order['num'])
        if order['agent']=='gtja' and order['ins']=='sell_order':
            r = auto_trade.gtja_sell(order['code'],order['price'],order['num'])
        if order['agent']=='cf' and order['ins']=='buy_order':
            r = auto_trade.cf_buy(order['code'],order['price'],order['num'])
        if order['agent']=='cf' and order['ins']=='sell_order':
            r = auto_trade.cf_sell(order['code'],order['price'],order['num'])

        if order['agent']=='pingan' and order['ins']=='avoid_idle':
            r = auto_trade.pingan_avoid_idle()
        if order['agent']=='cf' and order['ins']=='avoid_idle':
            r = auto_trade.cf_avoid_idle()

        if r == False:
            to_log('place_order: failed '+str(order))
        else:
            if order['ins'] != 'avoid_idle':
                append_order(str(order))
                record_order(order)
                to_log('place_order: success '+str(order))
    except Exception as e:
        print('error')
        print(e)

    return r

def place_order_service():
    print('place_order service begin...')
    address = ('localhost', 9002)     # family is deduced to be 'AF_INET'
    while True:
        with Listener(address, authkey=b'secret password') as listener:
            with listener.accept() as conn:
                #print('connection accepted from', listener.last_accepted)
                ins_dict = conn.recv(); #print(ins_dict)
                place_order(ins_dict)


def avoid_idle():
    print('avoid_idle begin ...')
    address = ('localhost', 9002)
    time.sleep(60)
    again = True
    while again:
        try :
            with Client(address, authkey=b'secret password') as conn:
                #print('here  2')
                ins_dict = {'ins':'avoid_idle','agent':'pingan'}
                conn.send(ins_dict)

                # time.sleep(9)
                # ins_dict = {'ins':'avoid_idle','agent':'cf'}
                # conn.send(ins_dict)
        except Exception as e:
            print('error')
            print(e)

        time.sleep(900)
        #print('here  1')


def on_order_done():
    print('on_order_done begin ...')
    pass

if __name__ == "__main__":
    p1 = multiprocessing.Process(target=place_order_service, args=())
    p1.start()
    time.sleep(1)

    p2 = multiprocessing.Process(target=avoid_idle, args=())
    p2.start()

    p3 = multiprocessing.Process(target=on_order_done, args=())
    p3.start()

    p1.join()
    p2.join()
    p3.join()
