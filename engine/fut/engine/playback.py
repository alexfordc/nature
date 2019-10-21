# encoding: UTF-8
from __future__ import print_function

from csv import DictReader
from datetime import datetime
from collections import OrderedDict, defaultdict

import os
import schedule
import time
from datetime import datetime
import numpy as np
import pandas as pd
import tushare as ts
import json
import threading
from multiprocessing.connection import Listener
from multiprocessing.connection import Client
import traceback

from nature import SOCKET_BAR
from nature import to_log, is_trade_day, send_email, get_dss
from nature import VtBarData, DIRECTION_LONG, DIRECTION_SHORT
from nature import Book, a_file

from nature import Fut_AtrRsiPortfolio
from nature import Gateway_Simnow_CTP
#from ipdb import set_trace



########################################################################
class BarGenerator(object):

    #----------------------------------------------------------------------
    def __init__(self, minx):
        """Constructor"""
        self.minx = minx
        self.bar_minx_dict = {}

    #----------------------------------------------------------------------
    def update_bar(self, new_bar):

        id = new_bar.vtSymbol
        if id in self.bar_minx_dict:
            bar = self.bar_minx_dict[id]
        else:
            bar = new_bar
            self.bar_minx_dict[id] = bar
            return None

        # 更新数据
        if bar.high < new_bar.high:
            bar.high = new_bar.high
        if bar.low > new_bar.low:
            bar.low =  new_bar.low
        bar.close = new_bar.close

        if self.minx == 'min5' and new_bar.time[3:5] in ['05','10','15','20','25','30','35','40','45','50','55','00']:
            # 将 bar的分钟改为整点，推送并保存bar
            bar.time = new_bar.time[:-2] + '00'
            return self.bar_minx_dict.pop(id)
        elif self.minx == 'min15' and new_bar.time[3:5] in ['15','30','45','00']:
            # 将 bar的分钟改为整点，推送并保存bar
            bar.time = new_bar.time[:-2] + '00'
            return self.bar_minx_dict.pop(id)
        else:
            self.bar_minx_dict[id] = bar

        return None

    #----------------------------------------------------------------------
    def save_bar(self, bar):
        df = pd.DataFrame([bar.__dict__])
        cols = ['date','time','open','high','low','close','volume']
        df = df[cols]

        fname = get_dss() + 'fut/put/rec/' + self.minx + '_' + bar.vtSymbol + '.csv'
        if os.path.exists(fname):
            df.to_csv(fname, index=False, mode='a', header=False)
        else:
            df.to_csv(fname, index=False, mode='a')

########################################################################
class FutEngine(object):
    """
    交易引擎不间断运行。开市前，重新初始化引擎，并加载数据；闭市后，保存数据到文件。
    收到交易指令后，传给交易路由，完成实际下单交易。
    """

    #----------------------------------------------------------------------
    def __init__(self):
        """Constructor"""

        self.dss = get_dss()
        self.gateway = None                # 路由
        self.portfolio_list = []           # 组合
        self.vtSymbol_list = []            # 品种

        self.dataDict = OrderedDict()
        self.startDt = None
        self.endDt = None

        # 加载品种
        config = open(get_dss()+'fut/cfg/config.json')
        setting = json.load(config)
        symbols = setting['symbols']
        self.vtSymbol_list = symbols.split(',')

    #----------------------------------------------------------------------
    def setPeriod(self, startDt, endDt):
        """设置回测周期"""
        self.startDt = startDt
        self.endDt = endDt

    #----------------------------------------------------------------------
    def init_daily(self):
        """每日初始化交易引擎"""

        # 初始化组合
        self.portfolio_list = []
        self.loadPortfolio(Fut_AtrRsiPortfolio)

    #----------------------------------------------------------------------
    def loadPortfolio(self, PortfolioClass):
        """加载投资组合"""
        to_log('in FutEngine.loadPortfolio')

        p = PortfolioClass(self, self.vtSymbol_list, {})
        p.init()
        p.daily_open()
        self.portfolio_list.append(p)

    #----------------------------------------------------------------------
    def loadData(self):
        """加载数据"""
        for vtSymbol in self.vtSymbol_list:
            filename = get_dss( )+ 'fut/bar/min1_' + vtSymbol + '.csv'

            df = pd.read_csv(filename)
            for i, d in df.iterrows():
                #print(d)

                bar = VtBarData()
                bar.vtSymbol = vtSymbol
                bar.symbol = vtSymbol
                bar.open = float(d['open'])
                bar.high = float(d['high'])
                bar.low = float(d['low'])
                bar.close = float(d['close'])
                bar.volume = d['volume']

                date = str(d['date'])
                bar.date = date
                bar.time = str(d['time'])
                if '-' in date:
                    bar.datetime = datetime.strptime(bar.date + ' ' + bar.time, '%Y-%m-%d %H:%M:%S')
                else:
                    bar.datetime = datetime.strptime(bar.date + ' ' + bar.time, '%Y%m%d %H:%M:%S')

                bar.datetime = datetime.strftime(bar.datetime, '%Y%m%d %H:%M:%S')

                barDict = self.dataDict.setdefault(bar.datetime, OrderedDict())
                barDict[bar.vtSymbol] = bar

                # break

    # -----------------------------------------------------------
    def run_playback(self):
        g5 = BarGenerator('min5')

        for dt, barDict in self.dataDict.items():
            if dt <= self.startDt or dt >=  self.endDt:
                continue
            #print(dt)
            try:
                for bar in barDict.values():
                    bar_min5 = g5.update_bar(bar)
                    if bar_min5 is not None:
                        g5.save_bar(bar_min5)
                        for p in self.portfolio_list:
                            p.onBar(bar_min5, 'min5')

                    for p in self.portfolio_list:
                        p.onBar(bar, 'min1')

            except Exception as e:
                print('-'*30)
                #traceback.print_exc()
                s = traceback.format_exc()
                print(s)

                # 对文件并发访问，存着读空文件的可能！！！
                print('file error ')

    #----------------------------------------------------------------------
    def _bc_loadInitBar(self, vtSymbol, initBars, minx):
        """反调函数，因引擎知道数据在哪，初始化Bar数据，"""

        assert minx == 'min5'

        dt_list = self.dataDict.keys()
        #print(dt_list)
        dt_list = [x for x in dt_list if x<self.startDt]
        dt_list = sorted(dt_list)
        init_dt_list = dt_list[-initBars:]
        # print(initBars)

        r = []
        for dt in init_dt_list:
            bar_dict = self.dataDict[dt]
            if vtSymbol in bar_dict:
                bar = bar_dict[vtSymbol]
                r.append(bar)


        return r

    #----------------------------------------------------------------------
    def _bc_sendOrder(self, vtSymbol, direction, offset, price, volume, pfName):
        """记录交易数据（由portfolio调用）"""

        # 记录成交数据
        dt = time.strftime('%Y-%m-%d %H:%M:%S',time.localtime())
        time.sleep(0.1)
        order_id = str(int(time.time()))

        r = [[dt,pfName,order_id,'minx',vtSymbol, direction, offset, price, volume]]
        print('send order: ', r)
        fn = 'fut/deal/engine_deal.csv'
        a_file(fn, str(r)[2:-2])

        if self.gateway is not None:
            self.gateway._bc_sendOrder(vtSymbol, direction, offset, price, volume, pfName)

    #----------------------------------------------------------------------
    def worker_open(self):
        """盘前加载配置及数据"""
        self.init_daily()

    #----------------------------------------------------------------------
    def worker_close(self):
        """盘后保存及展示数据"""


        self.gateway = None                # 路由

        self.vtSymbol_list = []

        # 保存信号参数
        for p in self.portfolio_list:
            p.daily_close()
        self.portfolio_list = []           # 组合

    #----------------------------------------------------------------------
def start():

    print(u'期货交易引擎开始回放')

    start_date = '20191017 21:00:00'
    end_date   = '20191018 15:00:00'

    e = FutEngine()
    e.setPeriod(start_date, end_date)
    e.loadData()

    e.worker_open()
    e.run_playback()
    e.worker_close()

if __name__ == '__main__':
    start()