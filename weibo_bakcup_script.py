# _*_coding:utf-8_*_
# !/usr/bin/env python3

from PIL import Image
import requests
from bs4 import BeautifulSoup
from http.cookiejar import LWPCookieJar
import os
import re
from pymongo import MongoClient


cookie_file = "cookies"
start_url = 'http://www.weibo.cn'
mobile = os.environ.get('MOBILE') or 'your_mobile_phone_number'
password = os.environ.get('PASSWORD') or 'your_password'
userid = os.environ.get('USERID') or 'your_id'
profile_url = "http://weibo.cn/" + userid + "/profile?vt=4"
proxies = {
    "http": "socks5://127.0.0.1:1080"
}


def get_my_weibo_url(filter, page):
    """filter: 1 为原创，2 为图片"""
    return "http://weibo.cn/" + userid + "/profile?filter={0}&page={1}&vt=4".format(filter, page)


def get_login_link(start_url):
    """获取登录链接(post数据到该链接以登录)"""
    pub_inter = requests.get(start_url)
    pub_soup = BeautifulSoup(pub_inter.text)
    login_link = pub_soup.a.get('href')

    return login_link


def get_login_soup(login_link):
    login = requests.get(login_link)
    login_soup = BeautifulSoup(login.text, "lxml")

    return login_soup


def get_capcha(login_soup):
    """获取验证码"""
    capcha_img_link = login_soup.img.get('src')
    image = requests.get(capcha_img_link)
    capcha_img = Image.open(image, 'r')
    capcha_img.show()

    capacha = input("please input code: ")
    capcha_img.close()
    return capacha


def get_login_content(login_soup, mobile, capacha, password, remember='on'):
    """制作登录表单"""
    login_content = {}

    for input_tag in login_soup.find_all('input'):
        key = input_tag.get('name')
        value = input_tag.get('value')
        login_content[key] = value

    login_content['mobile'] = mobile
    login_content['code'] = capacha
    login_content['remember'] = remember

    for items in login_content.keys():
        if 'password' in items:
            login_content[items] = password

    return login_content


def get_headers():
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6) "
                             "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/52.0.2743.116 Safari/537.36"}
    return headers


def is_login_successed(session):
    profile = session.get(profile_url)

    # 验证登录是否成功
    if profile.status_code == 200:
        return True
    else:
        return False


def get_session():
    # 使用session登录
    session = requests.Session()
    # session.proxies = proxies
    session.headers.update(get_headers())
    session.cookies = LWPCookieJar(cookie_file)

    if not os.path.exists(cookie_file):
        relogin()
    else:
        session.cookies.load()

    return session


def relogin():
    # 获取登录链接
    login_link = get_login_link(start_url)
    # 获取login链接的bs4解析
    login_soup = get_login_soup(login_link)
    # 获取验证码
    capacha = get_capcha(login_soup)
    # 获取登录表单
    login_content = get_login_content(login_soup, mobile, capacha, password)
    session = requests.Session()
    # session.proxies = proxies
    session.headers.update(get_headers())
    session.cookies = LWPCookieJar(cookie_file)

    session.post(login_link, data=login_content)
    session.cookies.save()
    return session


def login():
    load_session = get_session()
    if not is_login_successed(load_session):
        # 登录
        new_session = relogin()
        # 检查登录是否成功
        if is_login_successed(new_session):
            return new_session
        else:
            print("login failed :(")
    else:
        return load_session


def parse_weibo(fd):

    re_forward = re.compile("转发\[(.*)\]")
    re_comments = re.compile("评论\[(.*)\]")
    re_pic = re.compile("原图.?")
    re_pages = re.compile('([0-9]+?)/([0-9]+?)页')

    # 转化成bs对象
    soup = BeautifulSoup(fd, "lxml")

    # 解析对象并形成数据 内容，时间，评论，转发， 图片
    all_info = soup.find_all("div", class_="c")

    # 获取page
    now_max_page = []
    forms = soup.find_all("form")
    for _ in forms:
        form_text = _.get_text()
        pages = re_pages.search(form_text)
        if pages:
            now_max_page.append(pages.groups()[0])
            now_max_page.append(pages.groups()[1])
            break

    # 解析结果
    result = []
    for weibo in all_info:

        article = {}
        # 取出id
        id = weibo.get('id')
        if id is None:
            continue
        article["id"] = id

        # 取出内容
        source = weibo.find("span", class_="ctt").get_text()
        article["source"] = source

        # 取出评论数量和链接
        for a_link in weibo.find_all("a"):
            text = a_link.get_text()
            link = a_link.get("href")
            if re_comments.match(text):
                comments_link = link
                article["comments_num"] = re_comments.match(text).groups()[0]
                article["comments_link"] = comments_link
            elif re_forward.match(text):
                forward_link = link
                article["forward_sum"] = re_forward.match(text).groups()[0]
                article["forward_link"] = forward_link
            elif re_pic.match(text):
                pic_link = link
                article["pic_link"] = pic_link
            else:
                continue

        # 解析发布时间和来源
        time_via = weibo.find("span", class_="ct").get_text()
        article["time_via"] = time_via

        result.append(article)

    return result, now_max_page


def parse_comments(comments):
    # 找出评论
    soup = BeautifulSoup(comments, "lxml")

    # 找出评论人
    cmts = soup.find_all("div", class_="c")

    all_comment = {}
    cmt_id = 0
    for cmt in cmts:
        who = cmt.a
        text = cmt.find("span", class_="ctt")
        time_via = cmt.find("span", class_="ct")

        if (who is None) or (text is None) or (time_via is None):
            continue
        # str因为mongodb只能string键
        all_comment[str(cmt_id)] = "{0}: {1} --{2}".format(who.get_text(), text.get_text(), time_via.get_text())
        cmt_id += 1
    return all_comment
    # 关闭文件
    # comments.close()


def parse_forwards(forwards):
    """ 4 和 7 maginc number
    因为懒得解析了，毕竟转发很少，所以直接用解析出的列表长度去除了不想要的
    """
    # 取出转发评论
    soup = BeautifulSoup(forwards, "lxml")
    # 格式化
    forwards = soup.find_all("div", class_="c")
    result = {}
    result_num = 0
    for forward in forwards:
        text = forward.get_text().split("\n")
        if 4 < len(text) <= 7:
            # str 同上
            result[str(result_num)] = ''.join(text)
            result_num += 1
    return result


def get_total_pages(login_session):
    # 获得原创微博的最大页码
    my_weibo = login_session.get(get_my_weibo_url(1, 1)).text
    _, now_max_page = parse_weibo(my_weibo)
    return now_max_page[1]


def backup(login_session, start=1, end=171):
    now_parse_page = 0

    # 准备数据库
    db_connectiong = MongoClient()
    db = db_connectiong.my_weibo
    collection = db.items

    # 设置循环防止超过最大页码
    try:  # TODO: 当链接被重置时重置连接（微博反爬） 147 147, int(now_max_page[1])+1
        for wb_page_num in range(start, end):
            now_parse_page = wb_page_num
            # 解析原创微博
            fd = login_session.get(get_my_weibo_url(1, wb_page_num)).text
            results, page = parse_weibo(fd)

            print("Parsed {0}/{1} weibo ...".format(page[0], page[1]))

            # 解析评论
            copy_results = results[:]
            for content in copy_results:
                # 取得评论链接-解析-构造数据结构
                comments_link = content['comments_link']
                comments = parse_comments(login_session.get(comments_link).text)
                content['comments'] = comments

                # 朋友圈微博不能转发,没有转发链接
                try:
                    # 取得转发链接 - 解析 - 构造数据结构
                    forwards_link = content['forward_link']
                    forwards_cmts = parse_forwards(login_session.get(forwards_link).text)
                    content['forward_cmts'] = forwards_cmts
                except KeyError:
                    print("No forward link, may friend circle only.")
                    content['forward_link'] = None
                    content['forward_cmts'] = None

                print("Parsed this weibo's comments and forwards comments.")

                # 写入数据库
                print("Saving data ...")
                try:
                    collection.insert(content)
                except Exception as e:
                    raise e
                print("{0} page saved, {1} pages left...".format(page[0], str(int(page[1]) - int(page[0]))))
    except (IndexError, ConnectionResetError):
        return now_parse_page
    finally:
        db_connectiong.close()


if __name__ == "__main__":
    login_in_session = login()
    if not login_in_session:
        print("Error!")
    else:
        print("Login success!")
        # do something fun
        now_error_page = 0
        max_page = get_total_pages(login_in_session)
        try:
            # 获取异常出现时的页码
            now_error_page = backup(login_in_session, 147, max_page)
        except (IndexError, ConnectionResetError):
            backup(login_in_session, now_error_page, max_page)