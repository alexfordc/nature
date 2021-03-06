# encoding: UTF-8

import os
import pandas as pd
from csv import DictReader
from collections import OrderedDict, defaultdict

from nature import to_log, get_dss, get_contract
from nature import DIRECTION_LONG,DIRECTION_SHORT,OFFSET_OPEN,OFFSET_CLOSE,OFFSET_CLOSETODAY,OFFSET_CLOSEYESTERDAY
from nature import ArrayManager, Signal, Portfolio, TradeData, SignalResult


########################################################################
class Fut_RsiBollSignal_Duo(Signal):

    #----------------------------------------------------------------------
    def __init__(self, portfolio, vtSymbol):
        self.type = 'duo'

        # 策略参数
        self.fixedSize = 1           # 每次交易的数量
        self.initBars = 100           # 初始化数据所用的天数
        self.minx = 'min5'

        self.bollWindow = 60
        self.bollDev = 3
        self.atrValue = None
        self.atrWindow = 10
        self.slMultiplier = 1.5                  # CF
        self.hard_stop_ratio = 0.001

        # 策略临时变量
        self.can_buy = False
        self.can_short = False

        self.bollUp = 0
        self.bollDown = 0

        # 需要持久化保存的变量
        self.cost = 0
        self.intraTradeHigh = 0                  # 移动止损用的持仓期内最高价
        self.intraTradeLow = 100E4
        self.stop = 0                            # 多头止损
        self.hard_stop = 0                       # 硬止损
        self.dida = 0

        Signal.__init__(self, portfolio, vtSymbol)

    #----------------------------------------------------------------------
    def load_param(self):
        filename = get_dss() +  'fut/engine/rsiboll/signal_rsiboll_param.csv'
        if os.path.exists(filename):
            df = pd.read_csv(filename)
            df = df[ df.pz == get_contract(self.vtSymbol).pz ]
            if len(df) > 0:
                rec = df.iloc[0,:]

    #----------------------------------------------------------------------
    def set_param(self, param_dict):
        if 'atrMaLength' in param_dict:
            self.atrMaLength = param_dict['atrMaLength']
            #print('成功设置策略参数 self.atrMaLength: ',self.atrMaLength)

    #----------------------------------------------------------------------
    def onBar(self, bar, minx='min5'):
        """新推送过来一个bar，进行处理"""

        self.bar = bar
        if minx == 'min1':
            self.on_bar_min1(bar)

        if minx == self.minx:
            self.on_bar_minx(bar)

    def on_bar_min1(self, bar):
        if bar.time in ['09:01:00','21:01:00']:
            if bar.open - self.am.closeArray[-1] > 100:
                self.paused = True

    def on_bar_minx(self, bar):
        self.am.updateBar(bar)
        if not self.am.inited:
            return

        #print('here')
        self.calculateIndicator()     # 计算指标
        self.generateSignal(bar)    # 触发信号，产生交易指令

    #----------------------------------------------------------------------
    def calculateIndicator(self):
        """计算技术指标"""

        self.bollUp, self.bollDown = self.am.boll(self.bollWindow, self.bollDev)
        boll_condition = True if self.bar.close > self.bollUp else False

        self.can_buy = False
        if boll_condition:
            self.can_buy = True

        atrArray = self.am.atr(1, array=True)
        self.atrValue = atrArray[-self.atrWindow:].mean()


        self.can_sell = False
        self.intraTradeHigh = max(self.intraTradeHigh, self.bar.close)
        self.stop = self.intraTradeHigh - self.atrValue * self.slMultiplier

        self.dida += 1
        if self.bar.close <= self.stop and self.unit > 0 and self.dida > 60:
            self.can_sell = True

        if self.bar.close <= self.hard_stop and self.unit > 0:
            self.can_sell = True


        r = [[self.bar.date,self.bar.time,self.bar.close,self.can_buy,self.can_sell,self.bollUp,self.bollDown,boll_condition,self.atrValue,self.intraTradeHigh,self.stop,self.hard_stop]]
        df = pd.DataFrame(r)
        filename = get_dss() +  'fut/engine/rsiboll/bar_rsiboll_duo_' + self.vtSymbol + '.csv'
        df.to_csv(filename, index=False, mode='a', header=False)

    # #----------------------------------------------------------------------
    def generateSignal(self, bar):
        # 当前无仓位
        if self.unit == 0:
            if self.can_buy == True and self.paused == False:
                self.dida = 0
                self.cost = bar.close
                self.intraTradeHigh = bar.close
                self.hard_stop = (1 - self.hard_stop_ratio) * bar.close
                self.buy(bar.close, self.fixedSize)

        # 持有多头仓位
        elif self.unit > 0:
            if self.can_sell == True:
                self.sell(bar.close, abs(self.unit))


    #----------------------------------------------------------------------
    def load_var(self):
        pz = str(get_contract(self.vtSymbol).pz)
        filename = get_dss() +  'fut/engine/rsiboll/signal_rsiboll_'+self.type+'_var_' + pz + '.csv'
        if os.path.exists(filename):
            df = pd.read_csv(filename)
            df = df[df.vtSymbol == self.vtSymbol]
            df = df.sort_values(by='datetime')
            df = df.reset_index()
            if len(df) > 0:
                rec = df.iloc[-1,:]            # 取最近日期的记录
                self.unit = rec.unit
                self.cost = rec.cost
                self.intraTradeHigh = rec.intraTradeHigh
                self.intraTradeLow = rec.intraTradeLow
                self.stop = rec.stop
                self.dida = rec.dida
                if rec.has_result == 1:
                    self.result = SignalResult()
                    self.result.unit = rec.result_unit
                    self.result.entry = rec.result_entry
                    self.result.exit = rec.result_exit
                    self.result.pnl = rec.result_pnl

    #----------------------------------------------------------------------
    def save_var(self):
        r = []
        if self.result is None:
            r = [ [self.portfolio.result.date, self.vtSymbol, self.unit, self.cost, \
                   self.intraTradeHigh, self.intraTradeLow, self.stop, self.dida, \
                   0, 0, 0, 0, 0 ] ]
        else:
            r = [ [self.portfolio.result.date, self.vtSymbol, self.unit, self.cost, \
                   self.intraTradeHigh, self.intraTradeLow, self.stop, self.dida, \
                   1, self.result.unit, self.result.entry, self.result.exit, self.result.pnl ] ]
        df = pd.DataFrame(r, columns=['datetime','vtSymbol','unit','cost', \
                                      'intraTradeHigh','intraTradeLow', 'stop', 'dida', \
                                      'has_result','result_unit','result_entry','result_exit', 'result_pnl'])
        pz = str(get_contract(self.vtSymbol).pz)
        filename = get_dss() +  'fut/engine/rsiboll/signal_rsiboll_'+self.type+'_var_' + pz + '.csv'
        if os.path.exists(filename):
            df.to_csv(filename, index=False, mode='a', header=False)
        else:
            df.to_csv(filename, index=False)


########################################################################
class Fut_RsiBollSignal_Kong(Signal):

    #----------------------------------------------------------------------
    def __init__(self, portfolio, vtSymbol):
        self.type = 'kong'

        # 策略参数
        self.fixedSize = 1           # 每次交易的数量
        self.initBars = 100           # 初始化数据所用的天数
        self.minx = 'min5'

        self.bollWindow = 60
        self.bollDev = 3
        self.atrValue = None
        self.atrWindow = 10
        self.slMultiplier = 1.5
        self.hard_stop_ratio = 0.001

        # 策略临时变量
        self.can_buy = False
        self.can_short = False

        self.bollUp = 0
        self.bollDown = 0

        # 需要持久化保存的变量
        self.cost = 0
        self.intraTradeHigh = 0                      # 移动止损用的持仓期内最高价
        self.intraTradeLow = 100E4                   # 持仓期内的最低点
        self.stop = 0                                # 多头止损
        self.hard_stop = 100E4                       # 硬止损
        self.dida = 0

        Signal.__init__(self, portfolio, vtSymbol)

    #----------------------------------------------------------------------
    def load_param(self):
        filename = get_dss() +  'fut/engine/rsiboll/signal_rsiboll_param.csv'
        if os.path.exists(filename):
            df = pd.read_csv(filename)
            df = df[ df.pz == get_contract(self.vtSymbol).pz ]
            if len(df) > 0:
                rec = df.iloc[0,:]
                #print('成功加载策略参数', self.rsiLength, self.trailingPercent, self.victoryPercent)

    #----------------------------------------------------------------------
    def set_param(self, param_dict):
        if 'atrMaLength' in param_dict:
            self.atrMaLength = param_dict['atrMaLength']
            #print('成功设置策略参数 self.atrMaLength: ',self.atrMaLength)

    #----------------------------------------------------------------------
    def onBar(self, bar, minx='min5'):
        """新推送过来一个bar，进行处理"""

        self.bar = bar
        if minx == 'min1':
            self.on_bar_min1(bar)

        if minx == self.minx:
            self.on_bar_minx(bar)


    def on_bar_min1(self, bar):
        # 开盘有大缺口，暂停开仓
        if bar.time in ['09:01:00','21:01:00']:
            if bar.open - self.am.closeArray[-1]  < -100:
                self.paused = True


    def on_bar_minx(self, bar):
        self.am.updateBar(bar)
        if not self.am.inited:
            return

        #print('here')
        self.calculateIndicator()     # 计算指标
        self.generateSignal(bar)    # 触发信号，产生交易指令

    #----------------------------------------------------------------------
    def calculateIndicator(self):
        """计算技术指标"""

        self.bollUp, self.bollDown = self.am.boll(self.bollWindow, self.bollDev)
        boll_condition = True if self.bar.close < self.bollDown else False

        self.can_short = False
        if boll_condition:
            self.can_short = True

        atrArray = self.am.atr(1, array=True)
        self.atrValue = atrArray[-self.atrWindow:].mean()

        self.can_cover = False
        self.intraTradeLow = min(self.intraTradeLow, self.bar.close)
        self.stop = self.intraTradeLow + self.atrValue * self.slMultiplier

        self.dida += 1
        if self.bar.close >= self.stop and self.unit < 0 and self.dida > 60:
            self.can_cover = True

        if self.bar.close >= self.hard_stop and self.unit < 0:
            self.can_cover = True

        r = [[self.bar.date,self.bar.time,self.bar.close,self.can_short,self.can_cover,self.bollUp,self.bollDown,boll_condition,self.atrValue,self.intraTradeHigh,self.stop,self.hard_stop]]
        df = pd.DataFrame(r)
        filename = get_dss() +  'fut/engine/rsiboll/bar_rsiboll_kong_' + self.vtSymbol + '.csv'
        df.to_csv(filename, index=False, mode='a', header=False)


    #----------------------------------------------------------------------
    def generateSignal(self, bar):

        # 当前无仓位
        if self.unit == 0:
            if self.can_short == True and self.paused == False:
                self.dida = 0
                self.cost = bar.close
                self.intraTradeLow = bar.close
                self.hard_stop = (1 + self.hard_stop_ratio) * bar.close
                self.short(bar.close, self.fixedSize)

        # 持有多头仓位
        elif self.unit < 0:
            if self.can_cover == True:
                self.cover(bar.close, abs(self.unit))

    #----------------------------------------------------------------------
    def load_var(self):
        pz = str(get_contract(self.vtSymbol).pz)
        filename = get_dss() +  'fut/engine/rsiboll/signal_rsiboll_'+self.type+'_var_' + pz + '.csv'
        if os.path.exists(filename):
            df = pd.read_csv(filename)
            df = df[df.vtSymbol == self.vtSymbol]
            df = df.sort_values(by='datetime')
            df = df.reset_index()
            if len(df) > 0:
                rec = df.iloc[-1,:]            # 取最近日期的记录
                self.unit = rec.unit
                self.cost = rec.cost
                self.intraTradeHigh = rec.intraTradeHigh
                self.intraTradeLow = rec.intraTradeLow
                self.stop = rec.stop
                self.dida = rec.dida
                if rec.has_result == 1:
                    self.result = SignalResult()
                    self.result.unit = rec.result_unit
                    self.result.entry = rec.result_entry
                    self.result.exit = rec.result_exit
                    self.result.pnl = rec.result_pnl

    #----------------------------------------------------------------------
    def save_var(self):
        r = []
        if self.result is None:
            r = [ [self.portfolio.result.date, self.vtSymbol, self.unit, self.cost, \
                   self.intraTradeHigh, self.intraTradeLow, self.stop, self.dida, \
                   0, 0, 0, 0, 0 ] ]
        else:
            r = [ [self.portfolio.result.date, self.vtSymbol, self.unit, self.cost, \
                   self.intraTradeHigh, self.intraTradeLow, self.stop, self.dida, \
                   1, self.result.unit, self.result.entry, self.result.exit, self.result.pnl ] ]
        df = pd.DataFrame(r, columns=['datetime','vtSymbol','unit','cost', \
                                      'intraTradeHigh','intraTradeLow', 'stop', 'dida', \
                                      'has_result','result_unit','result_entry','result_exit', 'result_pnl'])
        pz = str(get_contract(self.vtSymbol).pz)
        filename = get_dss() +  'fut/engine/rsiboll/signal_rsiboll_'+self.type+'_var_' + pz + '.csv'
        if os.path.exists(filename):
            df.to_csv(filename, index=False, mode='a', header=False)
        else:
            df.to_csv(filename, index=False)


########################################################################
class Fut_RsiBollPortfolio(Portfolio):

    #----------------------------------------------------------------------
    def __init__(self, engine, symbol_list, signal_param={}):
        self.name = 'rsiboll'
        Portfolio.__init__(self, Fut_RsiBollSignal_Duo, engine, symbol_list, signal_param, Fut_RsiBollSignal_Kong, signal_param)
        #Portfolio.__init__(self, Fut_RsiBollSignal_Duo, engine, symbol_list, signal_param, None, None)
        #Portfolio.__init__(self, Fut_RsiBollSignal_Kong, engine, symbol_list, signal_param, None, None)



    #----------------------------------------------------------------------
    def _bc_newSignal(self, signal, direction, offset, price, volume):
        """
        对交易信号进行过滤，符合条件的才发单执行。
        计算真实交易价格和数量。
        """
        multiplier = self.portfolioValue * 0.01 / get_contract(signal.vtSymbol).size
        multiplier = int(round(multiplier, 0))
        #print(multiplier)
        multiplier = 1

        #print(self.posDict)
        # 计算合约持仓
        if direction == DIRECTION_LONG:
            self.posDict[signal.vtSymbol] += volume*multiplier
        else:
            self.posDict[signal.vtSymbol] -= volume*multiplier

        #print(self.posDict)

        # 对价格四舍五入
        priceTick = get_contract(signal.vtSymbol).price_tick
        price = int(round(price/priceTick, 0)) * priceTick
        price_deal = price
        if direction == DIRECTION_LONG:
            price_deal += 3*priceTick
        if direction == DIRECTION_SHORT:
            price_deal -= 3*priceTick


        self.engine._bc_sendOrder(signal.vtSymbol, direction, offset, price_deal, volume*multiplier, self.name)

        # 记录成交数据
        trade = TradeData(self.result.date, signal.vtSymbol, direction, offset, price, volume*multiplier)
        # l = self.tradeDict.setdefault(self.result.date, [])
        # l.append(trade)

        self.result.updateTrade(trade)
