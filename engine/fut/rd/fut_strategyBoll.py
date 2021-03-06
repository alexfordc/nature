# encoding: UTF-8

from csv import DictReader
from collections import defaultdict

from nature import to_log
from nature import ArrayManager
from nature import DIRECTION_LONG,DIRECTION_SHORT,OFFSET_OPEN,OFFSET_CLOSE,OFFSET_CLOSETODAY,OFFSET_CLOSEYESTERDAY
from nature import Signal, Portfolio

########################################################################
class Fut_BollSignal(Signal):

    #----------------------------------------------------------------------
    def __init__(self, portfolio, vtSymbol):
        Signal.__init__(self, portfolio, vtSymbol)

        # 策略参数
        self.bollWindow = 18                     # 布林通道窗口数
        self.bollDev = 3.4                       # 布林通道的偏差
        self.cciWindow = 10                      # CCI窗口数
        self.atrWindow = 30                      # ATR窗口数
        self.slMultiplier = 5.2                  # 计算止损距离的乘数
        self.initBars = 90           # 初始化数据所用的天数
        self.fixedSize = 1           # 每次交易的数量

        # 策略变量
        self.bollUp = 0                          # 布林通道上轨
        self.bollDown = 0                        # 布林通道下轨
        self.cciValue = 0                        # CCI指标数值
        self.atrValue = 0                        # ATR指标数值

        # 需要持久化保存的参数
        self.counter = 0
        self.buyPrice = 0
        self.intraTradeHigh = 0                  # 移动止损用的持仓期内最高价
        self.intraTradeLow = 100E4                   # 持仓期内的最低点
        self.longStop = 100E4                        # 多头止损
        self.shortStop = 0                       # 空头止损

        # 载入历史数据，并采用回放计算的方式初始化策略数值
        initData = self.portfolio.engine._bc_loadInitBar(self.vtSymbol, self.initBars)
        for bar in initData:
            self.bar = bar
            self.am.updateBar(bar)

    #----------------------------------------------------------------------
    def onBar(self, bar):
        """新推送过来一个bar，进行处理"""
        #print(bar.date, self.vtSymbol)

        self.bar = bar
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
        self.cciValue = self.am.cci(self.cciWindow)
        self.atrValue = self.am.atr(self.atrWindow)

    #----------------------------------------------------------------------
    def generateSignal(self, bar):
        # 判断是否要进行交易
        """
        cci>100，买入；
        买入后，6日内cci<100，卖出;
        cci<-100，卖出；
        """
        pos = self.portfolio.posDict[self.vtSymbol]

        # 当前无仓位，发送开仓委托
        if pos == 0:
            self.intraTradeHigh = bar.high
            self.intraTradeLow = bar.low

            if self.cciValue > 0 and bar.close > self.bollUp:
                self.buy(bar.close, self.fixedSize)

            elif self.cciValue < 0 and bar.close < self.bollDown:
                self.short(bar.close, self.fixedSize)

        # 持有多头仓位
        elif pos > 0:
            self.intraTradeHigh = max(self.intraTradeHigh, bar.high)
            self.intraTradeLow = bar.low
            self.longStop = self.intraTradeHigh - self.atrValue * self.slMultiplier

            if bar.close <= self.longStop:
                self.sell(bar.close, abs(pos))

        # 持有空头仓位
        elif pos < 0:
            self.intraTradeHigh = bar.high
            self.intraTradeLow = min(self.intraTradeLow, bar.low)
            self.shortStop = self.intraTradeLow + self.atrValue * self.slMultiplier

            if bar.close >= self.shortStop:
                self.cover(bar.close, abs(pos))

class Fut_BollPortfolio(Portfolio):
    #----------------------------------------------------------------------
    def __init__(self, engine, name):
        Portfolio.__init__(self, engine)

        self.name = name
        self.vtSymbolList = []
        self.SIZE_DICT = {}
        self.PRICETICK_DICT = {}
        self.VARIABLE_COMMISSION_DICT = {}
        self.FIXED_COMMISSION_DICT = {}
        self.SLIPPAGE_DICT = {}

    #----------------------------------------------------------------------
    def init(self):
        """初始化信号字典、持仓字典"""
        filename = self.engine.dss + 'fut/cfg/setting_fut_' + self.name + '.csv'

        with open(filename,encoding='utf-8') as f:
            r = DictReader(f)
            for d in r:
                self.vtSymbolList.append(d['vtSymbol'])
                self.SIZE_DICT[d['vtSymbol']] = int(d['size'])
                self.PRICETICK_DICT[d['vtSymbol']] = float(d['priceTick'])
                self.VARIABLE_COMMISSION_DICT[d['vtSymbol']] = float(d['variableCommission'])
                self.FIXED_COMMISSION_DICT[d['vtSymbol']] = float(d['fixedCommission'])
                self.SLIPPAGE_DICT[d['vtSymbol']] = float(d['slippage'])

        self.portfolioValue = 100E4

        for vtSymbol in self.vtSymbolList:
            self.posDict[vtSymbol] = 0
            signal1 = Fut_BollSignal(self, vtSymbol)
            l = self.signalDict[vtSymbol]
            l.append(signal1)

        print(u'投资组合的合约代码%s' %(self.vtSymbolList))

    #----------------------------------------------------------------------
    def _bc_newSignal(self, signal, direction, offset, price, volume):
        """
        对交易信号进行过滤，符合条件的才发单执行。
        计算真实交易价格和数量。
        """
        multiplier = 1

        # 计算合约持仓
        if direction == DIRECTION_LONG:
            self.posDict[signal.vtSymbol] += volume
        else:
            self.posDict[signal.vtSymbol] -= volume

        # 对价格四舍五入
        priceTick = self.PRICETICK_DICT[signal.vtSymbol]
        price = int(round(price/priceTick, 0)) * priceTick

        self.engine._bc_sendOrder(signal.vtSymbol, direction, offset, price, volume*multiplier)

    #----------------------------------------------------------------------
    def loadParam(self):
        filename = self.engine.dss + 'fut/cfg/AtrRsi_param.csv'
        df = pd.read_csv(filename)
        for i, row in df.iterrows():
            code = row.vtSymbol
            for signal in self.portfolio.signalDict[code]:
                signal.buyPrice = row.buyPrice,
                signal.intraTradeLow = row.intraTradeLow
                signal.longStop = row.longStop

    #----------------------------------------------------------------------
    def saveParam(self):
        r = []
        for code in self.vtSymbolList:
            if self.posDict[code] != 0:   #有持仓需保存参数
                for signal in self.portfolio.signalDict[code]:
                    r.append([code, signal.buyPrice, signal.intraTradeLow, signal.longStop])

        df = pd.DataFrame(r, columns=['vtSymbol','buyPrice','intraTradeLow','longStop'])
        filename = self.engine.dss + 'fut/cfg/AtrRsi_param.csv'
        df.to_csv(filename, index=False)
