# -*- encoding: utf-8 -*
from datetime import datetime
import logging
import random
import requests
from pyquery import PyQuery as pq
from worker import *
from article import *
from mongoengine import *
import math
import time

logging = logging.getLogger(__name__)


class FengWorker(Worker):
    def __init__(self, startdate=date(2015, 1, 1), enddate=date(2015, 1, 2)):
        super(FengWorker, self).__init__()
        self.beginDate = startdate
        self.endDate = enddate

    # http://news.ifeng.com/listpage/11528/20150311/2/rtlist.shtml
    # 大陆 11528 国际 11574 即时 11502
    __listUrl = 'http://news.ifeng.com/listpage/11528/{0}/{1}/rtlist.shtml'
    __referUrl = 'http://roll.news.qq.com/index.htm?site=news&mod=2&date={0}&cata='

    def start(self):
        self.get_records()
        day = self.beginDate
        while day <= self.endDate:
            if day not in self.historyDict:
                self.crawl_by_day(day)
            day += Worker.dayDelta

    def get_records(self):
        pass

    def crawl_by_day(self, day):
        page = 1
        date_str = day.strftime("%Y%m%d")
        # 当日首页
        try:
            r = requests.get(self.__listUrl.format(date_str, page))
            if r.status_code == 200:
                d = pq(r.text)
                self.parse_articles_list(d('.newsList'))
                # 循环分页
                while len(d('.newsList ul li')) == 60:
                    page += 1
                    r = requests.get(self.__listUrl.format(date_str, page))
                    d = pq(r.text)
                    self.parse_articles_list(d('.newsList'))
                self.save_by_day(date_str)
        except requests.exceptions.RequestException, e:
            logging.exception(e)
        except StandardError, e:
            logging.error(date_str + ' error')
            logging.exception(e)

    def parse_articles_list(self, articles):
        d = pq(articles)
        for i in range(0, d('ul li').length):
            li = d('ul li').eq(i)
            title = li('li a').text()
            link = li('li a').attr('href')

            item = {'title': title, 'link': link}
            self.newsDict[link] = item
            # 重试
            retry = 1
            try:
                self.get_detail(link)
            except StandardError:
                if retry > 0:
                    retry -= 1
                    self.get_detail(link)

    def get_detail(self, url):
        print(url)
        r = requests.get(url)
        r.encoding = 'utf-8'
        d = pq(r.text)
        source = ''
        source_link = ''
        self.newsDict[url]['summary'] = get_content_between(r.text, 'og:description" content="', '"/>')
        if d('#artical_real'):
            if d('#artical_sth .ss03 a'):
                source = d('#artical_sth .ss03 a').text()
                source_link = d('#artical_sth .ss03 a').attr.href
            self.newsDict[url]['source'] = source
            self.newsDict[url]['source_link'] = source_link
            # 可能会包含摘要，能移除的先移除
            if d('#main_content'):
                self.newsDict[url]['content'] = d('#main_content p').text()
            else:
                self.newsDict[url]['content'] = d('#artical_real p').text()
            self.newsDict[url]['image_links'] = [i.attr('src') for i in d.items('#artical_real p img')]
            self.newsDict[url]['video_links'] = [i.attr('flashvars') for i in d.items('#artical_real OBJECT embed')]
        nums = self.get_comment_num(url)
        self.newsDict[url]['comment_num'] = nums[0]
        self.newsDict[url]['reply_num'] = nums[1]

    # http://comment.ifeng.com/joincount.php?doc_url=http%3A%2F%2Fnews.ifeng.com%2Fa%2F20150623%2F44022615_0.shtml&format=js&callback=callbackGetFastCommentCount
    __commentNumUrl = 'http://comment.ifeng.com/joincount.php'

    def get_comment_num(self, url):
        payload = {'doc_url': url, 'format': 'js', 'callback': 'callbackGetFastCommentCount'}
        r = requests.get(self.__commentNumUrl, params=payload)
        if r.text.startswith('callbackGetFastCommentCount'):
            cont = get_content_between(r.text, '(', ')')
            nums = cont.split(',')
            if len(nums) > 1:
                return nums[0], nums[1]
            else:
                return nums[0], '0'
        else:
            return '0', '0'

    __commentNumUrlNew = 'http://coral.qq.com/article/{0}/commentnum'

    def save_by_day(self, date_str):
        connect('test')
        for k in self.newsDict:
            article = Article(link=self.newsDict[k]['link'], title=self.newsDict[k]['title'], post_date=date_str)
            article.summary = self.newsDict[k]['summary']
            article.source = self.newsDict[k]['source']
            article.source_link = self.newsDict[k]['source_link']
            article.content = self.newsDict[k]['content']
            article.image_links = self.newsDict[k]['image_links']
            article.video_links = self.newsDict[k]['video_links']
            article.comment_num = self.newsDict[k]['comment_num']
            article.reply_num = self.newsDict[k]['reply_num']
            article.save()