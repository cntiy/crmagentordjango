import hashlib
import json
import random
import string
import time
from urllib.parse import quote

from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse, JsonResponse, FileResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from .models import UserInfo, CrmLeads
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
    debug_mode = getattr(settings, 'DEBUG', False)

    corp_id = settings.QYWORK_CORP_ID
    agent_id = settings.QYWORK_AGENT_ID

    # 测试模式：没有 userid 时直接显示员工列表供选择，跳过 OAuth
    if debug_mode and not code and not userid:
        all_users = list(UserInfo.objects.all().order_by('department', 'name'))
        if all_users:
            userid = all_users[0].qw_id
        else:
            userid = 'test_user'

        user_name = userid
        try:
            user_info = UserInfo.objects.get(qw_id=userid)
            user_name = user_info.name or userid
        except UserInfo.DoesNotExist:
            pass

        return render(request, 'qywork/index.html', {
            'userid': userid,
            'user_name': user_name,
            'debug_mode': True,
            'all_users': all_users,
        })

    # 第一步：没有 code 也没有 userid → 跳 OAuth（生产环境）
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
        print(f"\n[OAuth] 员工登录:")
        print(json.dumps(user_data, ensure_ascii=False, indent=2))
        return redirect(f"/?userid={userid}")

    # 第三步：有 userid → 渲染页面 + 注入 JS SDK 配置
    page_url = request.build_absolute_uri()
    noncestr = rand_str()
    timestamp = int(time.time())
    agent_ticket = get_agent_ticket()
    agent_sig = make_signature(agent_ticket, noncestr, timestamp, page_url)

    # 查询员工信息
    try:
        user_info = UserInfo.objects.get(qw_id=userid)
        user_name = user_info.name or userid
        crm_user_id = user_info.crm_user_id or ''
    except UserInfo.DoesNotExist:
        user_name = userid
        crm_user_id = ''

    # 测试模式下加载所有员工供切换
    all_users = []
    if debug_mode:
        all_users = list(UserInfo.objects.all().order_by('department', 'name'))

    return render(request, 'qywork/index.html', {
        'userid': userid,
        'user_name': user_name,
        'debug_mode': debug_mode,
        'all_users': all_users,
        'corp_id': corp_id,
        'agent_id': agent_id,
        'noncestr': noncestr,
        'timestamp': timestamp,
        'agent_sig': agent_sig,
    })


def api_leads(request):
    """根据企微 userid 返回该销售负责的 CRM 线索"""
    userid = request.GET.get('userid', '')
    stage_filter = request.GET.get('stage', '')
    keyword = request.GET.get('keyword', '').strip()

    if not userid:
        return JsonResponse({'error': '缺少 userid 参数'}, status=400)

    # 查企微 userid → crm_user_id
    try:
        user_info = UserInfo.objects.get(qw_id=userid)
        crm_user_id = user_info.crm_user_id
    except UserInfo.DoesNotExist:
        return JsonResponse({'error': f'未找到企微用户 {userid}', 'leads': [], 'total': 0, 'active': 0, 'new_this_month': 0})

    if not crm_user_id:
        return JsonResponse({'error': '该用户未关联 CRM 账号', 'leads': [], 'total': 0, 'active': 0, 'new_this_month': 0})

    # 查该销售负责的线索（owner_primary 为 crm_user_id）
    qs = CrmLeads.objects.using('crm').filter(owner_primary=crm_user_id, is_deleted=0)

    # Tab 阶段过滤
    if stage_filter == 'following':
        qs = qs.filter(customer_stage__in=['following', 'negotiating', 'intention'])
    elif stage_filter == 'new':
        qs = qs.filter(leads_stage__in=['new', 'assigned', 'uncontacted'])
    elif stage_filter == 'deal':
        qs = qs.filter(leads_stage__icontains='deal') | qs.filter(biz_status_label='已成交')

    # 关键词搜索
    if keyword:
        qs = qs.filter(
            Q(name__icontains=keyword) |
            Q(company__icontains=keyword) |
            Q(mobile__icontains=keyword) |
            Q(tel__icontains=keyword)
        )

    # 统计数据（用原始全量 qs，不受 tab/keyword 过滤）
    base_qs = CrmLeads.objects.using('crm').filter(owner_primary=crm_user_id, is_deleted=0)
    total = base_qs.count()
    active = base_qs.exclude(leads_stage__in=['returned', 'lost', 'deal_done']).count()

    now = timezone.now()
    new_this_month = base_qs.filter(
        row_created_at__year=now.year,
        row_created_at__month=now.month
    ).count()

    # 取最多 200 条，按最后更新时间排序
    leads = list(qs.order_by('-row_updated_at')[:200].values(
        'id', 'name', 'mobile', 'tel', 'company',
        'leads_stage', 'leads_stage_label',
        'customer_stage', 'customer_stage_label',
        'biz_status_label', 'life_status_label',
        'last_follow_time', 'create_time', 'row_updated_at'
    ))

    # datetime 序列化
    for lead in leads:
        for k, v in lead.items():
            if hasattr(v, 'isoformat'):
                lead[k] = v.isoformat()

    return JsonResponse({
        'total': total,
        'active': active,
        'new_this_month': new_this_month,
        'leads': leads,
    })


def api_users(request):
    """测试用：返回所有员工列表（仅 DEBUG 模式开放）"""
    if not getattr(settings, 'DEBUG', False):
        return JsonResponse({'error': 'forbidden'}, status=403)

    users = list(UserInfo.objects.all().order_by('department', 'name').values(
        'qw_id', 'name', 'department', 'crm_user_id', 'position'
    ))
    return JsonResponse({'users': users, 'total': len(users)})


def api_contact(request):
    """获取外部联系人详情"""
    import httpx
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
    import httpx
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
