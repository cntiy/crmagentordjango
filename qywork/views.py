import hashlib
import json
import random
import string
import time
from urllib.parse import quote

from django.conf import settings
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse, FileResponse
from django.shortcuts import redirect

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

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>我的线索</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif; background: #f5f6f8; color: #333; }}

        .header {{ background: #1677ff; color: #fff; padding: 12px 16px; display: flex; align-items: center; justify-content: space-between; position: sticky; top: 0; z-index: 10; }}
        .header h1 {{ font-size: 16px; font-weight: 600; }}
        .header .user {{ font-size: 12px; opacity: 0.85; }}

        .tabs {{ display: flex; background: #fff; border-bottom: 1px solid #e8e8e8; }}
        .tab {{ flex: 1; text-align: center; padding: 10px 0; font-size: 13px; color: #666; cursor: pointer; border-bottom: 2px solid transparent; }}
        .tab.active {{ color: #1677ff; border-bottom-color: #1677ff; font-weight: 500; }}

        .search-bar {{ padding: 10px 12px; background: #fff; border-bottom: 1px solid #f0f0f0; }}
        .search-bar input {{ width: 100%; padding: 7px 12px; border: 1px solid #d9d9d9; border-radius: 20px; font-size: 13px; outline: none; }}
        .search-bar input:focus {{ border-color: #1677ff; }}

        .leads-list {{ padding: 8px 12px; }}
        .lead-card {{ background: #fff; border-radius: 8px; padding: 12px; margin-bottom: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }}
        .lead-card .name-row {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }}
        .lead-card .name {{ font-size: 15px; font-weight: 600; }}
        .lead-card .stage-tag {{ font-size: 11px; padding: 2px 8px; border-radius: 10px; background: #e6f4ff; color: #1677ff; }}
        .lead-card .stage-tag.won {{ background: #f6ffed; color: #52c41a; }}
        .lead-card .stage-tag.lost {{ background: #fff2f0; color: #ff4d4f; }}
        .lead-card .info-row {{ font-size: 12px; color: #888; margin-top: 4px; display: flex; gap: 12px; }}
        .lead-card .company {{ font-size: 13px; color: #555; margin-bottom: 4px; }}

        .empty {{ text-align: center; padding: 60px 20px; color: #bbb; }}
        .empty svg {{ width: 48px; height: 48px; margin-bottom: 12px; opacity: 0.4; }}
        .empty p {{ font-size: 14px; }}

        .loading {{ text-align: center; padding: 40px; color: #bbb; font-size: 14px; }}
        .load-more {{ text-align: center; padding: 12px; color: #1677ff; font-size: 13px; cursor: pointer; }}

        .stats-bar {{ display: flex; background: #fff; padding: 10px 0; border-bottom: 1px solid #f0f0f0; }}
        .stat-item {{ flex: 1; text-align: center; }}
        .stat-item .num {{ font-size: 18px; font-weight: 700; color: #1677ff; }}
        .stat-item .label {{ font-size: 11px; color: #999; margin-top: 2px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>我的线索</h1>
        <span class="user">{user_name}</span>
    </div>

    <div class="stats-bar">
        <div class="stat-item"><div class="num" id="stat-total">-</div><div class="label">总线索</div></div>
        <div class="stat-item"><div class="num" id="stat-active">-</div><div class="label">跟进中</div></div>
        <div class="stat-item"><div class="num" id="stat-new">-</div><div class="label">本月新增</div></div>
    </div>

    <div class="tabs">
        <div class="tab active" data-stage="">全部</div>
        <div class="tab" data-stage="following">跟进中</div>
        <div class="tab" data-stage="new">待联系</div>
        <div class="tab" data-stage="deal">已成交</div>
    </div>

    <div class="search-bar">
        <input type="text" id="search-input" placeholder="搜索姓名、公司、手机号..." />
    </div>

    <div class="leads-list" id="leads-list">
        <div class="loading">加载中...</div>
    </div>

    <script>
    const userid = '{userid}';
    let currentStage = '';
    let currentPage = 1;
    let searchTimer = null;
    let allLeads = [];

    function stageTag(label, stage) {{
        let cls = 'stage-tag';
        if (stage && (stage.includes('deal') || stage.includes('won') || label === '已成交')) cls += ' won';
        if (stage && (stage.includes('lost') || stage.includes('return') || label === '已退回')) cls += ' lost';
        return `<span class="${{cls}}">${{label || '未知阶段'}}</span>`;
    }}

    function renderCard(lead) {{
        const name = lead.name || '未知客户';
        const company = lead.company || '';
        const mobile = lead.mobile || lead.tel || '';
        const stageLabel = lead.leads_stage_label || lead.customer_stage_label || '';
        const stage = lead.leads_stage || '';
        const followTime = lead.last_follow_time ? lead.last_follow_time.slice(0, 10) : '';
        const createTime = lead.create_time ? lead.create_time.slice(0, 10) : '';
        return `
        <div class="lead-card">
            <div class="name-row">
                <span class="name">${{name}}</span>
                ${{stageTag(stageLabel, stage)}}
            </div>
            ${{company ? `<div class="company">🏢 ${{company}}</div>` : ''}}
            <div class="info-row">
                ${{mobile ? `<span>📱 ${{mobile}}</span>` : ''}}
                ${{followTime ? `<span>跟进: ${{followTime}}</span>` : createTime ? `<span>创建: ${{createTime}}</span>` : ''}}
            </div>
        </div>`;
    }}

    function renderList(leads) {{
        const container = document.getElementById('leads-list');
        if (!leads.length) {{
            container.innerHTML = `<div class="empty">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M9 17H7A5 5 0 017 7h1M15 7h1a5 5 0 010 10h-1M9 12h6"/></svg>
                <p>暂无线索</p>
            </div>`;
            return;
        }}
        container.innerHTML = leads.map(renderCard).join('');
    }}

    function loadLeads() {{
        const keyword = document.getElementById('search-input').value.trim();
        const url = `/api/leads?userid=${{encodeURIComponent(userid)}}&stage=${{currentStage}}&keyword=${{encodeURIComponent(keyword)}}`;
        fetch(url)
            .then(r => r.json())
            .then(data => {{
                if (data.error) {{
                    document.getElementById('leads-list').innerHTML = `<div class="empty"><p>⚠️ ${{data.error}}</p></div>`;
                    return;
                }}
                allLeads = data.leads || [];
                renderList(allLeads);
                document.getElementById('stat-total').textContent = data.total || 0;
                document.getElementById('stat-active').textContent = data.active || 0;
                document.getElementById('stat-new').textContent = data.new_this_month || 0;
            }})
            .catch(() => {{
                document.getElementById('leads-list').innerHTML = `<div class="empty"><p>加载失败，请刷新重试</p></div>`;
            }});
    }}

    // Tab 切换
    document.querySelectorAll('.tab').forEach(tab => {{
        tab.addEventListener('click', () => {{
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            currentStage = tab.dataset.stage;
            loadLeads();
        }});
    }});

    // 搜索防抖
    document.getElementById('search-input').addEventListener('input', () => {{
        clearTimeout(searchTimer);
        searchTimer = setTimeout(loadLeads, 400);
    }});

    // 初始加载
    loadLeads();
    </script>
</body>
</html>"""
    return HttpResponse(html)


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
    qs = CrmLeads.objects.filter(owner_primary=crm_user_id, is_deleted=0)

    # Tab 阶段过滤
    if stage_filter == 'following':
        qs = qs.filter(customer_stage__in=['following', 'negotiating', 'intention'])
    elif stage_filter == 'new':
        qs = qs.filter(leads_stage__in=['new', 'assigned', 'uncontacted'])
    elif stage_filter == 'deal':
        qs = qs.filter(leads_stage__icontains='deal') | qs.filter(biz_status_label='已成交')

    # 关键词搜索
    if keyword:
        from django.db.models import Q
        qs = qs.filter(
            Q(name__icontains=keyword) |
            Q(company__icontains=keyword) |
            Q(mobile__icontains=keyword) |
            Q(tel__icontains=keyword)
        )

    # 统计数据（用原始全量 qs，不受 tab/keyword 过滤）
    base_qs = CrmLeads.objects.filter(owner_primary=crm_user_id, is_deleted=0)
    total = base_qs.count()
    active = base_qs.exclude(leads_stage__in=['returned', 'lost', 'deal_done']).count()

    from django.utils import timezone
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
