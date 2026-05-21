import hashlib
import random
import string
import time
from urllib.parse import quote

from django.conf import settings
from django.http import HttpResponse, JsonResponse, FileResponse
from django.shortcuts import redirect
from django.views import View

from .services import get_access_token, get_agent_ticket


def rand_str(n=16):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def make_signature(ticket, noncestr, timestamp, url):
    s = f"jsapi_ticket={ticket}&noncestr={noncestr}&timestamp={timestamp}&url={url}"
    return hashlib.sha1(s.encode()).hexdigest()


def verify_domain(request):
    """企业微信域名验证文件"""
    verify_file = settings.QYWORK_VERIFY_FILE
    return FileResponse(open(verify_file, 'rb'))


def index(request):
    code = request.GET.get('code')
    userid = request.GET.get('userid')

    corp_id = settings.QYWORK_CORP_ID
    agent_id = settings.QYWORK_AGENT_ID

    # 第一步：没有 code 也没有 userid → 跳 OAuth
    if not code and not userid:
        base_url = request.build_absolute_uri('/')
        oauth_url = (
            f"https://open.weixin.qq.com/connect/oauth2/authorize"
            f"?appid={corp_id}"
            f"&redirect_uri={quote(base_url, safe='')}"
            f"&response_type=code"
            f"&scope=snsapi_base"
            f"&agentid={agent_id}"
            f"&state=sidebar"
            f"#wechat_redirect"
        )
        return redirect(oauth_url)

    # 第二步：拿到 code → 换员工 userid → 重定向到干净 URL
    if code:
        import httpx
        token = get_access_token()
        with httpx.Client() as client:
            resp = client.get(
                "https://qyapi.weixin.qq.com/cgi-bin/user/getuserinfo",
                params={"access_token": token, "code": code}
            )
            user_data = resp.json()
        userid = user_data.get("UserId", "unknown")
        import json
        print(f"\n[OAuth] 员工登录:")
        print(json.dumps(user_data, ensure_ascii=False, indent=2))
        return redirect(f"/?userid={userid}")

    # 第三步：有 userid → 渲染页面 + 注入 JS SDK 配置
    page_url = request.build_absolute_uri()
    noncestr = rand_str()
    timestamp = int(time.time())
    agent_ticket = get_agent_ticket()
    agent_sig = make_signature(agent_ticket, noncestr, timestamp, page_url)

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>企微侧边栏</title>
    <style>body{{font-family:sans-serif;padding:16px;}}pre{{background:#f5f5f5;padding:8px;border-radius:4px;overflow:auto;}}</style>
</head>
<body>
    <p>员工ID: <b>{userid}</b></p>
    <p>联系人: <span id="contact">获取中...</span></p>
    <pre id="detail"></pre>

    <script src="https://res.wx.qq.com/open/js/jweixin-1.2.0.js"></script>
    <script>
    function doAgentConfig() {{
        wx.agentConfig({{
            corpid: '{corp_id}',
            agentid: '{agent_id}',
            timestamp: {timestamp},
            nonceStr: '{noncestr}',
            signature: '{agent_sig}',
            jsApiList: ['getCurExternalContact', 'getCurExternalChat'],
            success: function() {{
                wx.invoke('getCurExternalContact', {{}}, function(res) {{
                    if (res.err_msg === 'getCurExternalContact:ok') {{
                        document.getElementById('contact').innerText = res.userId;
                        fetch('/api/contact?external_userid=' + res.userId + '&userid={userid}')
                            .then(r => r.json())
                            .then(data => {{
                                document.getElementById('detail').innerText = JSON.stringify(data, null, 2);
                            }});
                    }} else {{
                        wx.invoke('getCurExternalChat', {{}}, function(r) {{
                            if (r.err_msg === 'getCurExternalChat:ok') {{
                                document.getElementById('contact').innerText = '群聊: ' + r.chatId;
                                fetch('/api/groupchat?chat_id=' + r.chatId + '&userid={userid}')
                                    .then(resp => resp.json())
                                    .then(data => {{
                                        document.getElementById('detail').innerText = JSON.stringify(data, null, 2);
                                    }});
                            }} else {{
                                document.getElementById('contact').innerText = '失败: ' + r.err_msg;
                            }}
                        }});
                    }}
                }});
            }},
            fail: function(res) {{
                document.getElementById('contact').innerText = 'agentConfig 失败: ' + JSON.stringify(res);
            }}
        }});
    }}
    doAgentConfig();
    </script>
</body>
</html>"""
    return HttpResponse(html)


def api_contact(request):
    """获取外部联系人详情"""
    import httpx, json
    external_userid = request.GET.get('external_userid', '')
    userid = request.GET.get('userid', '')
    token = get_access_token()
    with httpx.Client() as client:
        resp = client.get(
            "https://qyapi.weixin.qq.com/cgi-bin/externalcontact/get",
            params={"access_token": token, "external_userid": external_userid}
        )
        data = resp.json()
    print(f"\n[联系人] 员工 [{userid}] 查看 [{external_userid}]:")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return JsonResponse(data)


def api_groupchat(request):
    """获取群聊详情"""
    import httpx, json
    chat_id = request.GET.get('chat_id', '')
    userid = request.GET.get('userid', '')
    token = get_access_token()
    with httpx.Client() as client:
        resp = client.post(
            "https://qyapi.weixin.qq.com/cgi-bin/externalcontact/groupchat/get",
            params={"access_token": token},
            json={"chat_id": chat_id}
        )
        data = resp.json()
    print(f"\n[群聊] 员工 [{userid}] 查看群 [{chat_id}]:")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    if data.get("errcode") == 92002:
        return JsonResponse({"error": "该群由外部企业创建，无法获取群信息"})
    return JsonResponse(data)
