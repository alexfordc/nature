# encoding: UTF-8
from __future__ import print_function

from datetime import datetime
from collections import OrderedDict, defaultdict
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from nature import get_stk_hfq, to_log, get_dss
from nature import VtBarData, DIRECTION_LONG, DIRECTION_SHORT, BarGenerator
from nature import Fut_AtrRsiPortfolio, Fut_RsiBollPortfolio, Fut_AberrationPortfolio
from nature import Fut_DonchianPortfolio, Fut_TurtlePortfolio, Fut_CciBollPortfolio

########################################################################
class BacktestingEngine(object):
    """组合类CTA策略回测引擎"""

    #----------------------------------------------------------------------
    def __init__(self,symbol_list,minx='min5'):
        """Constructor"""
        self.dss = get_dss()

        self.portfolio = None                # 一对一
        self.startDt = None
        self.endDt = None
        self.backtest_dt_list = []
        self.dataDict = OrderedDict()
        self.symbol_list = symbol_list
        self.minx = minx

    #----------------------------------------------------------------------
    def loadPortfolio(self, PortfolioClass, signal_param):
        """每日重新加载投资组合"""
        print('\n')

        p = PortfolioClass(self, self.symbol_list, signal_param)
        self.portfolio = p

    #----------------------------------------------------------------------
    def setPeriod(self, startDt, endDt):
        """设置回测周期"""
        self.startDt = startDt
        self.endDt = endDt

    #----------------------------------------------------------------------
    def loadData(self):
        """加载数据"""
        for vtSymbol in self.symbol_list:
            filename = get_dss( )+ 'fut/bar/min1_' + vtSymbol + '.csv'

            df = pd.read_csv(filename)
            for i, d in df.iterrows():
                # print(d)
                # print('here')

                bar = VtBarData()
                bar.vtSymbol = vtSymbol
                bar.symbol = vtSymbol
                bar.open = float(d['open'])
                bar.high = float(d['high'])
                bar.low = float(d['low'])
                bar.close = float(d['close'])
                bar.volume = d['volume']

                dt = d['datetime']

                bar.date =  dt[:4] + dt[5:7] + dt[8:10]
                bar.time =  dt[11:19]
                bar.datetime = bar.date + ' ' + bar.time
                # print(bar.datetime, bar.date, bar.time)
                # return

                # date = str(d['date'])
                # bar.date = date
                # bar.time = str(d['time'])
                # if '-' in date:
                #     bar.datetime = datetime.strptime(bar.date + ' ' + bar.time, '%Y-%m-%d %H:%M:%S')
                # else:
                #     bar.datetime = datetime.strptime(bar.date + ' ' + bar.time, '%Y%m%d %H:%M:%S')
                #
                # #bar.time = '00:00:00'
                # #bar.datetime = bar.date + ' ' + bar.time
                # bar.datetime = datetime.strftime(bar.datetime, '%Y%m%d %H:%M:%S')

                barDict = self.dataDict.setdefault(bar.datetime, OrderedDict())
                barDict[bar.vtSymbol] = bar
                # break

        self.output(u'全部数据加载完成')

    #----------------------------------------------------------------------
    def _bc_loadInitBar(self, vtSymbol, initBars, minx):
        """读取startDt前n条Bar数据，用于初始化am"""

        assert minx != 'min1'
        r = []

        # 直接读取signal对应minx相关的文件。
        fname = self.dss + 'fut/bar/' + self.minx + '_' + vtSymbol + '.csv'
        #print(fname)
        df = pd.read_csv(fname)
        df['datetime'] = df['date'] + ' ' + df['time']
        df = df[df.datetime < self.startDt]
        assert len(df) >= initBars

        df = df.sort_values(by=['date','time'])
        df = df.iloc[-initBars:]
        #print(df)

        for i, row in df.iterrows():
            d = dict(row)
            # print(d)
            # print(type(d))
            bar = VtBarData()
            bar.__dict__ = d
            r.append(bar)

        return r

    #----------------------------------------------------------------------
    def runBacktesting(self):
        """运行回测"""

        g = BarGenerator(self.minx)

        #print(len(self.dataDict))

        for dt, barDict in self.dataDict.items():
            if dt < self.startDt or dt >  self.endDt:
                #print(dt)
                continue

            # print('here')
            for bar in barDict.values():
                bar_minx = g.update_bar(bar)
                if bar_minx is not None:
                    self.portfolio.onBar(bar_minx, self.minx)

                self.portfolio.onBar(bar, 'min1')

    #----------------------------------------------------------------------
    def calculateResult(self, annualDays=240):
        """计算结果"""
        self.output(u'开始统计回测结果')

        for result in self.portfolio.resultList:
            result.calculatePnl()

        resultList = self.portfolio.resultList
        dateList = [result.date for result in resultList]
        #print(dateList)

        startDate = dateList[0]
        endDate = dateList[-1]
        totalDays = len(dateList)

        profitDays = 0
        lossDays = 0
        endBalance = self.portfolio.portfolioValue
        highlevel = self.portfolio.portfolioValue
        totalNetPnl = 0
        totalCommission = 0
        totalSlippage = 0
        totalTradeCount = 0

        netPnlList = []
        balanceList = []
        highlevelList = []
        drawdownList = []
        ddPercentList = []
        returnList = []

        for result in resultList:
            if result.netPnl > 0:
                profitDays += 1
            elif result.netPnl < 0:
                lossDays += 1
            netPnlList.append(result.netPnl)

            prevBalance = endBalance
            endBalance += result.netPnl
            balanceList.append(endBalance)
            returnList.append(endBalance/prevBalance - 1)

            highlevel = max(highlevel, endBalance)
            highlevelList.append(highlevel)

            drawdown = endBalance - highlevel
            drawdownList.append(drawdown)
            ddPercentList.append(drawdown/highlevel*100)

            totalCommission += result.commission
            totalSlippage += result.slippage
            totalTradeCount += result.tradeCount
            totalNetPnl += result.netPnl

        maxDrawdown = min(drawdownList)
        maxDdPercent = min(ddPercentList)
        totalReturn = (endBalance / self.portfolio.portfolioValue - 1) * 100
        dailyReturn = np.mean(returnList) * 100
        annualizedReturn = dailyReturn * annualDays
        returnStd = np.std(returnList) * 100

        if returnStd:
            sharpeRatio = dailyReturn / returnStd * np.sqrt(annualDays*72)
        else:
            sharpeRatio = 0

        # 返回结果
        result = {
            'startDate': startDate,
            'endDate': endDate,
            'totalDays': totalDays,
            'profitDays': profitDays,
            'lossDays': lossDays,
            'endBalance': endBalance,
            'maxDrawdown': maxDrawdown,
            'maxDdPercent': maxDdPercent,
            'totalNetPnl': totalNetPnl,
            'dailyNetPnl': totalNetPnl/totalDays,
            'totalCommission': totalCommission,
            'dailyCommission': totalCommission/totalDays,
            'totalSlippage': totalSlippage,
            'dailySlippage': totalSlippage/totalDays,
            'totalTradeCount': totalTradeCount,
            'dailyTradeCount': totalTradeCount/totalDays,
            'totalReturn': totalReturn,
            'annualizedReturn': annualizedReturn,
            'dailyReturn': dailyReturn,
            'returnStd': returnStd,
            'sharpeRatio': sharpeRatio
            }

        timeseries = {
            'balance': balanceList,
            'return': returnList,
            'highLevel': highlevel,
            'drawdown': drawdownList,
            'ddPercent': ddPercentList,
            'date': dateList,
            'netPnl': netPnlList
        }

        return timeseries, result

    #----------------------------------------------------------------------
    def showResult(self):
        """显示回测结果"""
        timeseries, result = self.calculateResult()

        # 输出统计结果
        self.output('-' * 30)
        self.output(u'首个交易日：\t%s' % result['startDate'])
        self.output(u'最后交易日：\t%s' % result['endDate'])

        self.output(u'总交易日：\t%s' % result['totalDays'])
        self.output(u'盈利交易日\t%s' % result['profitDays'])
        self.output(u'亏损交易日：\t%s' % result['lossDays'])

        self.output(u'起始资金：\t%s' % self.portfolio.portfolioValue)
        self.output(u'结束资金：\t%s' % formatNumber(result['endBalance']))

        self.output(u'总收益率：\t%s%%' % formatNumber(result['totalReturn']))
        self.output(u'年化收益：\t%s%%' % formatNumber(result['annualizedReturn']))
        self.output(u'总盈亏：\t%s' % formatNumber(result['totalNetPnl']))
        self.output(u'最大回撤: \t%s' % formatNumber(result['maxDrawdown']))
        self.output(u'百分比最大回撤: %s%%' % formatNumber(result['maxDdPercent']))

        self.output(u'总手续费：\t%s' % formatNumber(result['totalCommission']))
        self.output(u'总滑点：\t%s' % formatNumber(result['totalSlippage']))
        self.output(u'总成交笔数：\t%s' % formatNumber(result['totalTradeCount']))

        self.output(u'日均盈亏：\t%s' % formatNumber(result['dailyNetPnl']))
        self.output(u'日均手续费：\t%s' % formatNumber(result['dailyCommission']))
        self.output(u'日均滑点：\t%s' % formatNumber(result['dailySlippage']))
        self.output(u'日均成交笔数：\t%s' % formatNumber(result['dailyTradeCount']))

        self.output(u'日均收益率：\t%s%%' % formatNumber(result['dailyReturn']))
        self.output(u'收益标准差：\t%s%%' % formatNumber(result['returnStd']))
        self.output(u'Sharpe Ratio：\t%s' % formatNumber(result['sharpeRatio']))

        # 绘图
        fig = plt.figure(figsize=(10, 16))

        pBalance = plt.subplot(4, 1, 1)
        pBalance.set_title('Balance')
        plt.plot(timeseries['date'], timeseries['balance'])

        pDrawdown = plt.subplot(4, 1, 2)
        pDrawdown.set_title('Drawdown')
        pDrawdown.fill_between(range(len(timeseries['drawdown'])), timeseries['drawdown'])

        pPnl = plt.subplot(4, 1, 3)
        pPnl.set_title('Daily Pnl')
        plt.bar(range(len(timeseries['drawdown'])), timeseries['netPnl'])

        pKDE = plt.subplot(4, 1, 4)
        pKDE.set_title('Daily Pnl Distribution')
        plt.hist(timeseries['netPnl'], bins=50)

        plt.show()

    #----------------------------------------------------------------------
    def _bc_sendOrder(self, vtSymbol, direction, offset, price, volume, pfName):
        """记录交易数据（由portfolio调用）"""

        pass

    #----------------------------------------------------------------------
    def output(self, content):
        """输出信息"""
        print(content)

    #----------------------------------------------------------------------
    def show_result_key(self):
        """返回回测信息"""
        timeseries, result = self.calculateResult()

        # 输出统计结果
        self.output('-' * 30)
        # self.output(u'首个交易日：\t%s' % result['startDate'])
        # self.output(u'最后交易日：\t%s' % result['endDate'])

        # self.output(u'起始资金：\t%s' % self.portfolio.portfolioValue)
        # self.output(u'结束资金：\t%s' % formatNumber(result['endBalance']))

        self.output(u'总收益率：\t%s%%' % formatNumber(result['totalReturn']))
        # self.output(u'总盈亏：\t%s' % formatNumber(result['totalNetPnl']))
        # self.output(u'最大回撤: \t%s' % formatNumber(result['maxDrawdown']))
        self.output(u'百分比最大回撤: %s%%' % formatNumber(result['maxDdPercent']))

        # self.output(u'总手续费：\t%s' % formatNumber(result['totalCommission']))
        # self.output(u'总滑点：\t%s' % formatNumber(result['totalSlippage']))
        self.output(u'总成交笔数：\t%s' % formatNumber(result['totalTradeCount']))

        self.output(u'Sharpe Ratio：\t%s' % formatNumber(result['sharpeRatio']))

        return result

    #----------------------------------------------------------------------
    def getTradeData(self, vtSymbol=''):
        """获取交易数据"""
        tradeList = []

        for l in self.tradeDict.values():
            for trade in l:
                if not vtSymbol:
                    tradeList.append(trade)
                elif trade.vtSymbol == vtSymbol:
                    tradeList.append(trade)

        return tradeList

#----------------------------------------------------------------------
def formatNumber(n):
    """格式化数字到字符串"""
    rn = round(n, 2)        # 保留两位小数
    return format(rn, ',')  # 加上千分符

def run_once(PortfolioClass,symbol,start_date,end_date,signal_param,minx):
    # 创建回测引擎对象
    e = BacktestingEngine([symbol], minx)
    e.setPeriod(start_date, end_date)
    e.loadData()
    e.loadPortfolio(PortfolioClass, signal_param)
    e.runBacktesting()
    return e.show_result_key()

def test_one(PortfolioClass, minx):
    # vtSymbol = 'CF001'
    # start_date = '20191014 21:00:00'
    # end_date   = '20191018 15:00:00'

    # vtSymbol = 'rb1901'
    # start_date = '20180515 00:00:00'
    # end_date   = '20181231 00:00:00'

    vtSymbol = 'CF901'
    vtSymbol = 'rb1901'
    start_date = '20180119 00:00:00'
    end_date   = '20181231 00:00:00'

    #signal_param = {vtSymbol:{'trailingPercent':0.6, 'victoryPercent':0.3}}
    signal_param = {}
    run_once(PortfolioClass,vtSymbol,start_date,end_date,signal_param,minx)

if __name__ == '__main__':
    # PortfolioClass = Fut_AtrRsiPortfolio
    # PortfolioClass = Fut_TurtlePortfolio
    # PortfolioClass = Fut_AberrationPortfolio
    # PortfolioClass = Fut_RsiBollPortfolio
    # PortfolioClass = Fut_DonchianPortfolio
    PortfolioClass = Fut_CciBollPortfolio

    minx = 'min15'
    #minx = 'min5'

    test_one(PortfolioClass, minx)
