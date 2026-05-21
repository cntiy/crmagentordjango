"""企微 access_token / agent_ticket 获取与签名工具。"""
import hashlib
import random
import string

import httpx
from django.conf import settings
from django.core.cache import cache

_TOKEN_KEY = "qywork:access_token"
_TICKET_KEY = "qywork:agent_ticket"


def get_access_token() -> str:
    token = cache.get(_TOKEN_KEY)
    if token:
        return token
    with httpx.Client(timeout=10) as client:
        resp = client.get(
            "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
            params={"corpid": settings.QYWORK_CORP_ID, "corpsecret": settings.QYWORK_AGENT_SECRET},
        )
        data = resp.json()
    if "access_token" not in data:
        raise RuntimeError(f"获取 access_token 失败: {data}")
    cache.set(_TOKEN_KEY, data["access_token"], timeout=data["expires_in"] - 60)
    return data["access_token"]


def get_agent_ticket() -> str:
    ticket = cache.get(_TICKET_KEY)
    if ticket:
        return ticket
    token = get_access_token()
    with httpx.Client(timeout=10) as client:
        resp = client.get(
            "https://qyapi.weixin.qq.com/cgi-bin/ticket/get",
            params={"access_token": token, "type": "agent_config"},
        )
        data = resp.json()
    if "ticket" not in data:
        raise RuntimeError(f"获取 agent ticket 失败: {data}")
    cache.set(_TICKET_KEY, data["ticket"], timeout=data["expires_in"] - 60)
    return data["ticket"]


def make_signature(ticket: str, noncestr: str, timestamp: int, url: str) -> str:
    s = f"jsapi_ticket={ticket}&noncestr={noncestr}&timestamp={timestamp}&url={url}"
    return hashlib.sha1(s.encode()).hexdigest()


def rand_str(n: int = 16) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def fetch_external_contact(external_userid: str) -> dict:
    token = get_access_token()
    with httpx.Client(timeout=10) as client:
        resp = client.get(
            "https://qyapi.weixin.qq.com/cgi-bin/externalcontact/get",
            params={"access_token": token, "external_userid": external_userid},
        )
        return resp.json()


def fetch_groupchat(chat_id: str) -> dict:
    token = get_access_token()
    with httpx.Client(timeout=10) as client:
        resp = client.post(
            "https://qyapi.weixin.qq.com/cgi-bin/externalcontact/groupchat/get",
            params={"access_token": token},
            json={"chat_id": chat_id},
        )
        return resp.json()


def fetch_userid_by_code(code: str) -> dict:
    token = get_access_token()
    with httpx.Client(timeout=10) as client:
        resp = client.get(
            "https://qyapi.weixin.qq.com/cgi-bin/user/getuserinfo",
            params={"access_token": token, "code": code},
        )
        return resp.json()
