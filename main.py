import json
import time
import argparse
import os
import logging

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

from utils import reserve, get_user_credentials

get_current_time = lambda action: (
    time.strftime("%H:%M:%S", time.localtime(time.time() + 8 * 3600))
    if action
    else time.strftime("%H:%M:%S", time.localtime(time.time()))
)
get_current_dayofweek = lambda action: (
    time.strftime("%A", time.localtime(time.time() + 8 * 3600))
    if action
    else time.strftime("%A", time.localtime(time.time()))
)


SLEEPTIME = 0.1  # 每次尝试座位之间的间隔
STARTTIME = "21:00:00"  # 北京时间：到这个时间才开始提交预约请求
ENDTIME = "21:05:00"  # 预约尝试截止时间

ENABLE_SLIDER = False  # 是否有滑块验证
MAX_ATTEMPT = 40  # reserve.submit 内部最大轮数
RESERVE_NEXT_DAY = False  # 预约明天而不是今天的


def prepare_sessions(users, usernames, passwords, action):
    """在预约开放前完成登录，返回已登录的会话；此处不提交预约请求。"""
    if action and (len(usernames.split(",")) != len(users) or len(passwords.split(",")) != len(users)):
        raise Exception("user number should match the number of config")

    current_dayofweek = get_current_dayofweek(action)
    sessions = [None] * len(users)

    for index, user in enumerate(users):
        username, password, times, roomid, seatid, daysofweek = user.values()
        if current_dayofweek not in daysofweek:
            logging.info("Today not set to reserve; skip this user")
            continue

        if action:
            username = usernames.split(",")[index]
            password = passwords.split(",")[index]

        logging.info(f"准备登录：{username}；预约时段：{times}；座位列表：{seatid}")
        session = reserve(
            sleep_time=SLEEPTIME,
            max_attempt=MAX_ATTEMPT,
            enable_slider=ENABLE_SLIDER,
            reserve_next_day=RESERVE_NEXT_DAY,
        )
        session.get_login_status()
        login_ok, login_message = session.login(username, password)
        if not login_ok:
            raise RuntimeError(f"账号登录失败，未开始预约：{login_message}")
        session.requests.headers.update({"Host": "office.chaoxing.com"})
        sessions[index] = session
        logging.info(f"{username} 登录准备完成；尚未提交预约请求")

    return sessions


def main(users, action=False):
    current_time = get_current_time(action)
    logging.info(f"start time {current_time}, action {'on' if action else 'off'}")
    usernames, passwords = (None, None)
    if action:
        usernames, passwords = get_user_credentials(action)

    current_dayofweek = get_current_dayofweek(action)
    active_indices = [
        i for i, user in enumerate(users)
        if current_dayofweek in user.get("daysofweek", [])
    ]
    if not active_indices:
        logging.info("Today not set to reserve for any configured user; exit")
        return

    # 提前完成登录和会话初始化；prepare_sessions 不会调用 submit。
    sessions = prepare_sessions(users, usernames, passwords, action)
    success_list = [False] * len(users)

    # GitHub Actions 预计北京时间20:58启动；等待到21:00再发起第一次预约提交。
    current_time = get_current_time(action)
    if current_time < STARTTIME:
        logging.info(f"登录准备已完成，等待北京时间 {STARTTIME} 开始预约")
        while current_time < STARTTIME:
            time.sleep(0.1)
            current_time = get_current_time(action)

    logging.info(f"到达预约开始时间：{current_time}；现在开始按配置顺序提交")

    attempt_times = 0
    while current_time < ENDTIME:
        attempt_times += 1
        for index in active_indices:
            if success_list[index]:
                continue

            user = users[index]
            _, _, times, roomid, seatid, _ = user.values()
            if isinstance(seatid, str):
                seatid = [seatid]

            logging.info(f"第 {attempt_times} 轮；即将按配置顺序尝试座位：{seatid}")
            success_list[index] = sessions[index].submit(times, roomid, seatid, action)

        print(
            f"attempt time {attempt_times}, time now {current_time}, success list {success_list}"
        )
        if all(success_list[i] for i in active_indices):
            logging.info("所有符合今天预约条件的账号均已预约成功")
            return

        current_time = get_current_time(action)

    logging.info(f"到达截止时间 {ENDTIME}；预约循环结束。最终结果：{success_list}")


def debug(users, action=False):
    logging.info(
        f"Global settings: \nSLEEPTIME: {SLEEPTIME}\nENDTIME: {ENDTIME}\nENABLE_SLIDER: {ENABLE_SLIDER}\nRESERVE_NEXT_DAY: {RESERVE_NEXT_DAY}"
    )
    if action:
        usernames, passwords = get_user_credentials(action)
    current_dayofweek = get_current_dayofweek(action)
    for index, user in enumerate(users):
        username, password, times, roomid, seatid, daysofweek = user.values()
        if isinstance(seatid, str):
            seatid = [seatid]
        if action:
            username, password = usernames.split(",")[index], passwords.split(",")[index]
        if current_dayofweek not in daysofweek:
            logging.info("Today not set to reserve")
            continue
        logging.info(f"----------- {username} -- {times} -- {seatid} try -----------")
        session = reserve(
            sleep_time=SLEEPTIME,
            max_attempt=MAX_ATTEMPT,
            enable_slider=ENABLE_SLIDER,
            reserve_next_day=RESERVE_NEXT_DAY,
        )
        session.get_login_status()
        session.login(username, password)
        session.requests.headers.update({"Host": "office.chaoxing.com"})
        if session.submit(times, roomid, seatid, action):
            return


def get_roomid(args1, args2):
    username = input("请输入用户名：")
    password = input("请输入密码：")
    session = reserve(
        sleep_time=SLEEPTIME,
        max_attempt=MAX_ATTEMPT,
        enable_slider=ENABLE_SLIDER,
        reserve_next_day=RESERVE_NEXT_DAY,
    )
    session.get_login_status()
    session.login(username=username, password=password)
    session.requests.headers.update({"Host": "office.chaoxing.com"})
    encode = input("请输入deptldEnc：")
    session.roomid(encode)


if __name__ == "__main__":
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    parser = argparse.ArgumentParser(prog="Chao Xing seat auto reserve")
    parser.add_argument("-u", "--user", default=config_path, help="user config file")
    parser.add_argument(
        "-m", "--method", default="reserve",
        choices=["reserve", "debug", "room"], help="for debug"
    )
    parser.add_argument(
        "-a", "--action", action="store_true",
        help="use --action to enable in github action"
    )
    args = parser.parse_args()
    func_dict = {"reserve": main, "debug": debug, "room": get_roomid}
    with open(args.user, "r", encoding="utf-8") as data:
        usersdata = json.load(data)["reserve"]
    func_dict[args.method](usersdata, args.action)
