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

from .models import UserInfo, CrmLeads, CrmFieldMapping
from .services import get_access_token, get_agent_ticket


# 超级管理员企微 userid（可查看所有线索）
SUPER_USERS = {'13510088891', 'Qi', 'yingxiaoxiaozu'}


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

    # 权限标识（超管 / 主管 / 普通员工）
    is_super = userid in SUPER_USERS
    is_manager = False
    try:
        ui = UserInfo.objects.get(qw_id=userid)
        is_manager = (ui.position == 2)
    except UserInfo.DoesNotExist:
        pass

    if is_super:
        user_name = f"{user_name}（全部）"
    elif is_manager:
        user_name = f"{user_name}（主管）"

    # 测试模式下加载所有员工供切换
    all_users = []
    if debug_mode:
        all_users = list(UserInfo.objects.all().order_by('department', 'name'))

    return render(request, 'qywork/index.html', {
        'userid': userid,
        'user_name': user_name,
        'debug_mode': debug_mode,
        'is_super': is_super,
        'is_manager': is_manager,
        'all_users': all_users,
        'corp_id': corp_id,
        'agent_id': agent_id,
        'noncestr': noncestr,
        'timestamp': timestamp,
        'agent_sig': agent_sig,
    })


def _resolve_visible_crm_ids(userid):
    """
    返回 (是否超管, 可见的 crm_user_id 列表 或 None=全部, 自己的 crm_user_id, 是否主管, 错误信息)
    - 超管 → 全部线索（visible=None）
    - 主管(position=2) → 同部门所有员工的 crm_user_id
    - 普通员工 → 仅自己的 crm_user_id
    """
    if userid in SUPER_USERS:
        return True, None, '', False, None

    try:
        user_info = UserInfo.objects.get(qw_id=userid)
    except UserInfo.DoesNotExist:
        return False, [], '', False, f'未找到企微用户 {userid}'

    if not user_info.crm_user_id:
        return False, [], '', False, '该用户未关联 CRM 账号'

    is_manager = (user_info.position == 2 and bool(user_info.department))
    own_crm_id = user_info.crm_user_id

    if is_manager:
        crm_ids = list(
            UserInfo.objects.filter(department=user_info.department)
            .exclude(crm_user_id__isnull=True)
            .exclude(crm_user_id='')
            .values_list('crm_user_id', flat=True)
        )
        return False, crm_ids, own_crm_id, True, None

    return False, [own_crm_id], own_crm_id, False, None


def api_leads(request):
    """根据企微 userid 返回该用户可见的 CRM 线索"""
    userid = request.GET.get('userid', '')
    stage_filter = request.GET.get('stage', '')
    keyword = request.GET.get('keyword', '').strip()

    if not userid:
        return JsonResponse({'error': '缺少 userid 参数'}, status=400)

    is_super, visible_crm_ids, own_crm_id, is_manager, err = _resolve_visible_crm_ids(userid)
    if err:
        return JsonResponse({'error': err, 'leads': [], 'total': 0, 'active': 0, 'new_this_month': 0})

    # 构造可见线索范围
    if is_super or visible_crm_ids is None:
        base_qs = CrmLeads.objects.using('crm').filter(is_deleted=0)
    else:
        base_qs = CrmLeads.objects.using('crm').filter(
            owner_primary__in=visible_crm_ids, is_deleted=0
        )

    qs = base_qs

    # Tab 阶段过滤
    if stage_filter == 'following':
        qs = qs.filter(biz_status_label='跟进中')
    elif stage_filter == 'new':
        qs = qs.filter(biz_status_label='待处理')
    elif stage_filter == 'deal':
        qs = qs.filter(biz_status_label='已转换')
    elif stage_filter == 'unassigned':
        qs = qs.filter(biz_status_label='未分配')
    elif stage_filter == 'mine':
        # 主管专用：仅看自己负责的
        if own_crm_id:
            qs = qs.filter(owner_primary=own_crm_id)
        else:
            qs = qs.none()

    # 关键词搜索
    if keyword:
        qs = qs.filter(
            Q(name__icontains=keyword) |
            Q(company__icontains=keyword) |
            Q(mobile__icontains=keyword) |
            Q(tel__icontains=keyword)
        )

    # 统计
    total = base_qs.count()
    active = base_qs.filter(biz_status_label='跟进中').count()
    now = timezone.now()
    new_this_month = base_qs.filter(
        create_time__year=now.year,
        create_time__month=now.month,
    ).count()

    # 取最多 200 条（按 raw_json 里的 last_modified_time 降序）
    leads = list(qs.order_by('-raw_json__last_modified_time')[:200].values(
        'id', 'name', 'mobile', 'tel', 'company',
        'leads_stage', 'leads_stage_label',
        'customer_stage', 'customer_stage_label',
        'biz_status_label', 'life_status_label',
        'last_follow_time', 'create_time', 'row_updated_at',
        'owner_primary',
    ))

    # 批量补 owner 姓名（避免 N+1）
    owner_ids = {l['owner_primary'] for l in leads if l.get('owner_primary')}
    owner_map = {}
    if owner_ids:
        owner_map = dict(
            UserInfo.objects.filter(crm_user_id__in=owner_ids)
            .values_list('crm_user_id', 'name')
        )

    for lead in leads:
        lead['owner_name'] = owner_map.get(lead.get('owner_primary'), '') or ''
        for k, v in lead.items():
            if hasattr(v, 'isoformat'):
                lead[k] = v.isoformat()

    return JsonResponse({
        'total': total,
        'active': active,
        'new_this_month': new_this_month,
        'leads': leads,
    })


def api_lead_detail(request):
    """线索详情，需做权限校验"""
    userid = request.GET.get('userid', '')
    lead_id = request.GET.get('id', '')

    if not userid or not lead_id:
        return JsonResponse({'error': '缺少参数'}, status=400)

    is_super, visible_crm_ids, own_crm_id, is_manager, err = _resolve_visible_crm_ids(userid)
    if err:
        return JsonResponse({'error': err}, status=403)

    try:
        lead = CrmLeads.objects.using('crm').get(id=lead_id, is_deleted=0)
    except CrmLeads.DoesNotExist:
        return JsonResponse({'error': '线索不存在'}, status=404)

    # 非超管要校验线索归属
    if not is_super and visible_crm_ids is not None:
        if lead.owner_primary not in visible_crm_ids:
            return JsonResponse({'error': '无权查看此线索'}, status=403)

    # 仅显示在 crm_field_mapping 表里有 label 的线索字段
    mappings = list(
        CrmFieldMapping.objects.using('crm')
        .filter(object_api='LeadsObj')
        .exclude(label__isnull=True).exclude(label='')
        .exclude(db_column__isnull=True).exclude(db_column='')
        .values('db_column', 'label', 'field_type', 'data_type')
    )

    # 模型字段名集合（用于校验 db_column 是否存在于 model 上）
    model_field_names = {
        f.attname for f in lead._meta.get_fields() if hasattr(f, 'attname')
    }

    items = []
    for m in mappings:
        col = m['db_column']
        if col == 'raw_json' or col not in model_field_names:
            continue
        v = getattr(lead, col, None)
        if hasattr(v, 'isoformat'):
            v = v.isoformat()
        # 空值不显示
        if v is None or v == '' or v == [] or v == {}:
            continue
        items.append({
            'key': col,
            'label': m['label'],
            'value': v,
        })

    # 负责人姓名（不在映射表里，单独补一条插在最前面）
    owner_name = ''
    if lead.owner_primary:
        owner = UserInfo.objects.filter(crm_user_id=lead.owner_primary).first()
        owner_name = owner.name if owner else ''
    if owner_name:
        items.insert(0, {'key': 'owner_name', 'label': '负责人', 'value': owner_name})

    return JsonResponse({
        'lead': {'name': lead.name or '', 'id': lead.id},
        'groups': [{'title': '线索详情', 'items': items}] if items else [],
    })


def api_match_lead(request):
    """
    根据当前聊天的外部联系人匹配 CRM 线索。
    流程：external_userid → 调企微 API 拿姓名/手机 → 在权限范围内查 crm_leads。
    匹配策略：手机号优先 → 姓名+公司兜底。
    权限：与列表一致（普通员工/主管不能越权看；超管全开）。
    """
    import re
    userid = request.GET.get('userid', '')
    external_userid = request.GET.get('external_userid', '')

    if not userid or not external_userid:
        return JsonResponse({'error': '缺少参数'}, status=400)

    is_super, visible_crm_ids, own_crm_id, is_manager, err = _resolve_visible_crm_ids(userid)
    if err:
        return JsonResponse({'error': err}, status=403)

    # 调企微拿外部联系人信息
    try:
        from .services import fetch_external_contact
        ext = fetch_external_contact(external_userid)
    except Exception as e:
        return JsonResponse({'error': f'获取外部联系人失败: {e}'}, status=500)

    print(f"\n[match] 员工 [{userid}] 当前会话外部联系人 [{external_userid}] 原始返回:")
    print(json.dumps(ext, ensure_ascii=False, indent=2))

    if ext.get('errcode') != 0:
        return JsonResponse({'error': f"企微接口错误: {ext.get('errmsg', ext)}"}, status=500)

    info = ext.get('external_contact', {}) or {}
    contact_name = info.get('name', '') or ''
    # 手机号在 follow_user[].remark_mobiles 或 external_profile，企微不直接给，先尝试 unionid 留空
    # 真实手机号通常需要客户主动提供，先从 external_profile 里拿
    contact_corp = info.get('corp_name', '') or ''  # 客户所在公司（如果是企业微信用户）

    # 尝试多个可能的手机字段
    contact_mobile = ''
    profile = info.get('external_profile') or {}
    for ext_attr in profile.get('external_attr', []) or []:
        if ext_attr.get('type') == 0 and '电话' in ext_attr.get('name', ''):
            contact_mobile = (ext_attr.get('text') or {}).get('value', '')
            break

    # 可见线索范围
    if is_super or visible_crm_ids is None:
        base_qs = CrmLeads.objects.using('crm').filter(is_deleted=0)
    else:
        base_qs = CrmLeads.objects.using('crm').filter(
            owner_primary__in=visible_crm_ids, is_deleted=0
        )

    # 1. 手机号精确匹配（去掉空格、+86 等）
    matched_in_visible = []  # 权限范围内匹配到的
    total_in_crm = 0  # 全库匹配到的总数（不限权限）
    match_by = ''

    if contact_mobile:
        mobile_clean = re.sub(r'\D', '', contact_mobile)
        if mobile_clean:
            tail = mobile_clean[-11:]  # 末 11 位（处理 +86 等前缀）
            # 全库查（不限权限）
            all_qs = CrmLeads.objects.using('crm').filter(
                Q(mobile__contains=tail) | Q(tel__contains=tail), is_deleted=0
            )
            total_in_crm = all_qs.count()
            # 权限范围内查
            qs = base_qs.filter(Q(mobile__contains=tail) | Q(tel__contains=tail))
            matched_in_visible = list(qs[:20])
            if matched_in_visible or total_in_crm:
                match_by = 'mobile'

    # 2. 兜底：姓名 + 公司模糊匹配
    if not match_by and contact_name:
        # 全库查
        all_qs = CrmLeads.objects.using('crm').filter(name__icontains=contact_name, is_deleted=0)
        if contact_corp:
            all_qs = all_qs.filter(company__icontains=contact_corp) | CrmLeads.objects.using('crm').filter(
                name__icontains=contact_name, company__isnull=True, is_deleted=0
            )
        total_in_crm = all_qs.count()
        # 权限范围内查
        qs = base_qs.filter(name__icontains=contact_name)
        if contact_corp:
            qs = qs.filter(company__icontains=contact_corp) | base_qs.filter(
                name__icontains=contact_name, company__isnull=True
            )
        matched_in_visible = list(qs[:20])
        if matched_in_visible or total_in_crm:
            match_by = 'name'

    # 序列化（与列表用同样的字段）
    if matched_in_visible:
        ids = [l.id for l in matched_in_visible]
        leads = list(
            CrmLeads.objects.using('crm').filter(id__in=ids).values(
                'id', 'name', 'mobile', 'tel', 'company',
                'leads_stage', 'leads_stage_label',
                'customer_stage', 'customer_stage_label',
                'biz_status_label', 'life_status_label',
                'last_follow_time', 'create_time', 'row_updated_at',
                'owner_primary',
            )
        )
        owner_ids = {l['owner_primary'] for l in leads if l.get('owner_primary')}
        owner_map = {}
        if owner_ids:
            owner_map = dict(
                UserInfo.objects.filter(crm_user_id__in=owner_ids)
                .values_list('crm_user_id', 'name')
            )
        for lead in leads:
            lead['owner_name'] = owner_map.get(lead.get('owner_primary'), '') or ''
            for k, v in lead.items():
                if hasattr(v, 'isoformat'):
                    lead[k] = v.isoformat()
    else:
        leads = []

    return JsonResponse({
        'contact': {
            'name': contact_name,
            'mobile': contact_mobile,
            'corp_name': contact_corp,
            'external_userid': external_userid,
        },
        'match_by': match_by,
        'total_in_crm': total_in_crm,  # 全库匹配数（不限权限）
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
