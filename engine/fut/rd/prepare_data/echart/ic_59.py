
import pyecharts.options as opts
from pyecharts.charts import Line, Kline, Bar, Grid, Scatter

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import talib

from nature import get_dss


def gen_line(df1, symbol, price_min, price_max):
    #df1['datetime'] = df1['date'] + ' ' + df1['time']
    df1['datetime'] = df1['date']
    dt_list =  list(df1['datetime'])
    close_list = df1.apply(lambda record: float(record['close']), axis=1).tolist()
    close_list = np.array(close_list)

    line1 = Line(init_opts=opts.InitOpts(height='700px',width='1300px'))
    line1.set_global_opts( yaxis_opts=opts.AxisOpts(min_=price_min,
                                                    #min_=999,
                                                    max_=price_max,
                                                    splitarea_opts=opts.SplitAreaOpts(is_show=True, areastyle_opts=opts.AreaStyleOpts(opacity=1)),
                                                    ),
                           datazoom_opts=[opts.DataZoomOpts(is_show=True,type_="slider",range_start=0,range_end=100,),],
                         )
    line1.add_xaxis( xaxis_data=dt_list )
    line1.add_yaxis( symbol, y_axis=close_list, )
    line1.set_series_opts(label_opts=opts.LabelOpts(is_show=False))

    return line1


def gen_ma(df1,n):
    df1['datetime'] = df1['date']
    dt_list =  list(df1['datetime'])
    close_list = df1.apply(lambda record: float(record['close']), axis=1).tolist()
    close_list = np.array(close_list)
    ma_n = talib.SMA(close_list, n)
    # print(ma_120)
    # print( type(ma_120) )

    line = Line()
    line.add_xaxis( xaxis_data=dt_list )
    line.add_yaxis( 'MA'+str(n), y_axis=ma_n,label_opts=opts.LabelOpts(is_show=False),)

    return line

def ic(symbol1, symbol2, start_dt, end_dt):
    fn = get_dss() +'backtest/fut/m/day_' + symbol1 + '.csv'
    df1 = pd.read_csv(fn)
    df1 = df1[(df1.date >= start_dt) & (df1.date <= end_dt)]
    df1 = df1.reset_index()
    # print(df1.head(3))

    fn = get_dss() +'backtest/fut/m/day_' + symbol2 + '.csv'
    df2 = pd.read_csv(fn)
    df2 = df2[(df2.date >= start_dt) & (df2.date <= end_dt)]
    df2 = df2.reset_index()
    # print(df2.head(3))

    df1['close'] = df1.close - df2.close
    # print(df1.close)
    price_min = df1['close'].min() - 100
    price_max =  df1['close'].max() + 100
    line1 = gen_line(df1, symbol1+'-'+symbol2, price_min, price_max)
    # line_ma  = gen_ma(df1, 10)

    fn = get_dss( )+ 'backtest/render/ic_' + symbol1 + '_'+ symbol2+ '.html'
    # line1.overlap(line_ma).render(fn)
    line1.render(fn)
    # line1.render( path='./漏斗图01.png' )
    # line1.render( path='./漏斗图02.jpg' )

def ic_59():
    symbol1 = 'm05'
    symbol2 = 'm09'
    start_dt = '2019-01-01'
    end_dt   = '2019-04-31'
    ic(symbol1, symbol2, start_dt, end_dt)

def ic_91():
    symbol1 = 'm09'
    symbol2 = 'm01'
    start_dt = '2018-05-01'
    end_dt   = '2018-08-31'
    ic(symbol1, symbol2, start_dt, end_dt)

# ic_59()
ic_91()
