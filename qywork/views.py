import hashlib
import json
import random
import re
import string
import time
from urllib.parse import quote

from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse, JsonResponse, FileResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import UserInfo, CrmLeads, CrmFieldMapping, QwSession, LeadSessionBind
from .services import (
    get_access_token,
    get_agent_ticket,
    fetch_external_contact,
    fetch_groupchat,
)


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


# ─────────────────────────────────────────────
# 辅助：从企微 externalcontact 原始返回提取手机和公司
# ─────────────────────────────────────────────

def _extract_contact_info(ext_data: dict, opener_userid: str) -> dict:
    """
    从企微 externalcontact/get 原始返回提取：
      name, type(1个微/2企微), mobile, corp_name, avatar
    mobile 来源优先级：
      1. follow_user[opener].remark_mobiles[0]
      2. external_profile.external_attr 里名字含"电话"的文本
    corp_name 来源：
      - 企微(type=2): external_contact.corp_name
      - 个微(type=1): follow_user[opener].remark_corp_name
    """
    info = ext_data.get('external_contact', {}) or {}
    follow_users = ext_data.get('follow_user', []) or []

    name = info.get('name', '') or ''
    contact_type = info.get('type', 0)  # 1=个微 2=企微
    avatar = info.get('avatar', '') or ''

    # corp_name
    if contact_type == 2:
        corp_name = info.get('corp_name', '') or ''
    else:
        # 个微：找当前打开侧边栏的销售的 remark_corp_name
        corp_name = ''
        for fu in follow_users:
            if fu.get('userid') == opener_userid:
                corp_name = fu.get('remark_corp_name', '') or ''
                break

    # mobile：优先 remark_mobiles
    mobile = ''
    for fu in follow_users:
        if fu.get('userid') == opener_userid:
            rm = fu.get('remark_mobiles') or []
            if rm:
                mobile = rm[0]
                break

    # 回退到 external_profile.external_attr
    if not mobile:
        profile = info.get('external_profile') or {}
        for attr in profile.get('external_attr', []) or []:
            if attr.get('type') == 0 and '电话' in attr.get('name', ''):
                mobile = (attr.get('text') or {}).get('value', '') or ''
                break

    return {
        'name': name,
        'type': contact_type,
        'mobile': mobile,
        'corp_name': corp_name,
        'avatar': avatar,
    }


def _serialize_leads(lead_objs_or_qs):
    """将 CrmLeads queryset/列表序列化为前端卡片格式"""
    if not lead_objs_or_qs:
        return []
    if hasattr(lead_objs_or_qs, 'values'):
        rows = list(lead_objs_or_qs.values(
            'id', 'name', 'mobile', 'tel', 'company',
            'leads_stage', 'leads_stage_label',
            'customer_stage', 'customer_stage_label',
            'biz_status_label', 'life_status_label',
            'last_follow_time', 'create_time', 'row_updated_at',
            'owner_primary',
        ))
    else:
        ids = [l.id for l in lead_objs_or_qs]
        rows = list(CrmLeads.objects.using('crm').filter(id__in=ids).values(
            'id', 'name', 'mobile', 'tel', 'company',
            'leads_stage', 'leads_stage_label',
            'customer_stage', 'customer_stage_label',
            'biz_status_label', 'life_status_label',
            'last_follow_time', 'create_time', 'row_updated_at',
            'owner_primary',
        ))
    owner_ids = {r['owner_primary'] for r in rows if r.get('owner_primary')}
    owner_map = {}
    if owner_ids:
        owner_map = dict(
            UserInfo.objects.filter(crm_user_id__in=owner_ids)
            .values_list('crm_user_id', 'name')
        )
    for r in rows:
        r['owner_name'] = owner_map.get(r.get('owner_primary'), '') or ''
        for k, v in r.items():
            if hasattr(v, 'isoformat'):
                r[k] = v.isoformat()
    return rows


def _upsert_session(session_type: str, external_id: str, opener_userid: str,
                    name: str = '', contact_type: int = 0,
                    corp_name: str = '', mobile: str = '', raw_info: dict = None) -> 'QwSession':
    """
    Upsert qw_session 表：
    - session_type: 'contact' | 'group'
    - external_id: external_userid 或 chat_id
    """
    from django.utils import timezone as tz
    now = tz.now()
    session, created = QwSession.objects.get_or_create(
        session_type=session_type,
        external_id=external_id,
        defaults={
            'name': name,
            'contact_type': contact_type,
            'corp_name': corp_name,
            'mobile': mobile,
            'raw_info': raw_info or {},
            'first_opened_by': opener_userid,
            'last_opened_by': opener_userid,
            'first_opened_at': now,
            'last_opened_at': now,
        }
    )
    if not created:
        # 更新可能变化的字段
        update_fields = ['last_opened_by', 'last_opened_at']
        session.last_opened_by = opener_userid
        session.last_opened_at = now
        if name and not session.name:
            session.name = name
            update_fields.append('name')
        if mobile and not session.mobile:
            session.mobile = mobile
            update_fields.append('mobile')
        if corp_name and not session.corp_name:
            session.corp_name = corp_name
            update_fields.append('corp_name')
        if raw_info:
            session.raw_info = raw_info
            update_fields.append('raw_info')
        session.save(update_fields=update_fields)
    return session


def _match_leads_by_contact(external_id: str, contact_info: dict,
                             base_qs, bound_lead_ids: set) -> tuple:
    """
    对单个外部联系人用 mobile/company/name 匹配线索。
    返回 (m2_leads_list, match_by)，结果已排除 bound_lead_ids。
    """
    mobile = contact_info.get('mobile', '') or ''
    corp_name = contact_info.get('corp_name', '') or ''
    name = contact_info.get('name', '') or ''
    match_by = ''
    matched = []

    if mobile:
        tail = re.sub(r'\D', '', mobile)[-11:]
        if tail:
            qs = base_qs.filter(Q(mobile__contains=tail) | Q(tel__contains=tail))
            if bound_lead_ids:
                qs = qs.exclude(id__in=bound_lead_ids)
            matched = list(qs[:20])
            if matched:
                match_by = 'mobile'

    if not match_by:
        if name and corp_name:
            qs = base_qs.filter(name__icontains=name, company__icontains=corp_name)
            if bound_lead_ids:
                qs = qs.exclude(id__in=bound_lead_ids)
            matched = list(qs[:20])
            if matched:
                match_by = 'name+company'

    if not match_by and mobile:
        # 仅手机已试过没中，这里跳过
        pass

    if not match_by and name and not corp_name:
        qs = base_qs.filter(name__icontains=name)
        if bound_lead_ids:
            qs = qs.exclude(id__in=bound_lead_ids)
        matched = list(qs[:20])
        if matched:
            match_by = 'name'

    return matched, match_by


def api_match_lead(request):
    """
    三模块匹配视图（个人 & 群通用入口）。
    GET 参数：
      userid        - 打开侧边栏的销售企微 userid（必填）
      external_userid - 个人聊天时的外部联系人 userid（个人场景）
      chat_id       - 群聊时的 chat_id（群场景）
    返回：
      session_id, session_type, contact
      m1_leads  - 已绑定线索
      m2_leads  - 未绑定但匹配（仅个人）
      match_by  - 匹配依据描述
    """
    userid = request.GET.get('userid', '')
    external_userid = request.GET.get('external_userid', '')
    chat_id = request.GET.get('chat_id', '')

    if not userid:
        return JsonResponse({'error': '缺少 userid 参数'}, status=400)
    if not external_userid and not chat_id:
        return JsonResponse({'error': '缺少 external_userid 或 chat_id'}, status=400)

    is_super, visible_crm_ids, own_crm_id, is_manager, err = _resolve_visible_crm_ids(userid)
    if err:
        return JsonResponse({'error': err}, status=403)

    # 可见线索范围（M2 用）
    if is_super or visible_crm_ids is None:
        base_qs = CrmLeads.objects.using('crm').filter(is_deleted=0)
    else:
        base_qs = CrmLeads.objects.using('crm').filter(
            owner_primary__in=visible_crm_ids, is_deleted=0
        )

    # ── 个人会话 ──────────────────────────────
    if external_userid:
        # 获取外部联系人信息
        try:
            ext_data = fetch_external_contact(external_userid)
        except Exception as e:
            return JsonResponse({'error': f'获取外部联系人失败: {e}'}, status=500)

        print(f"\n[match] 员工 [{userid}] 当前会话外部联系人 [{external_userid}] 原始返回:")
        print(json.dumps(ext_data, ensure_ascii=False, indent=2))

        if ext_data.get('errcode') != 0:
            return JsonResponse({'error': f"企微接口错误: {ext_data.get('errmsg', ext_data)}"}, status=500)

        contact_info = _extract_contact_info(ext_data, userid)

        # Upsert 会话记录
        session = _upsert_session(
            session_type='contact',
            external_id=external_userid,
            opener_userid=userid,
            name=contact_info['name'],
            contact_type=contact_info['type'],
            corp_name=contact_info['corp_name'],
            mobile=contact_info['mobile'],
            raw_info=ext_data,
        )

        # M1：已绑定线索
        bound_ids_qs = LeadSessionBind.objects.filter(session=session).values_list('lead_id', flat=True)
        bound_lead_ids = set(bound_ids_qs)
        m1_leads = _serialize_leads(
            CrmLeads.objects.using('crm').filter(id__in=bound_lead_ids, is_deleted=0)
        ) if bound_lead_ids else []

        # M2：未绑定但匹配（权限范围内，排除已绑定）
        m2_objs, match_by = _match_leads_by_contact(external_userid, contact_info, base_qs, bound_lead_ids)
        m2_leads = _serialize_leads(m2_objs)

        return JsonResponse({
            'session_id': session.id,
            'session_type': 'contact',
            'contact': {
                'name': contact_info['name'],
                'type': contact_info['type'],
                'mobile': contact_info['mobile'],
                'corp_name': contact_info['corp_name'],
                'external_userid': external_userid,
            },
            'm1_leads': m1_leads,
            'm2_leads': m2_leads,
            'match_by': match_by,
        })

    # ── 群会话 ────────────────────────────────
    else:
        try:
            group_data = fetch_groupchat(chat_id)
        except Exception as e:
            return JsonResponse({'error': f'获取群信息失败: {e}'}, status=500)

        print(f"\n[群聊] 员工 [{userid}] 查看群 [{chat_id}]:")
        print(json.dumps(group_data, ensure_ascii=False, indent=2))

        if group_data.get('errcode') == 92002:
            return JsonResponse({'error': '该群由外部企业创建，无法获取群信息'}, status=403)
        if group_data.get('errcode') != 0:
            return JsonResponse({'error': f"企微接口错误: {group_data.get('errmsg', group_data)}"}, status=500)

        gc = group_data.get('group_chat', {}) or {}
        group_name = gc.get('name', '') or ''

        # Upsert 群 session
        session = _upsert_session(
            session_type='group',
            external_id=chat_id,
            opener_userid=userid,
            name=group_name,
            raw_info=group_data,
        )

        # 群里所有 type=2 的外部联系人 external_userid
        member_list = gc.get('member_list', []) or []
        ext_member_ids = [m['userid'] for m in member_list if m.get('type') == 2 and m.get('userid')]

        # M1_direct：直接绑在群 session 上的线索（手工绑定产生）
        direct_bound_ids = set(
            LeadSessionBind.objects.filter(session=session).values_list('lead_id', flat=True)
        )

        # M1_via_contact：群成员的 contact session 上已绑定的线索
        via_contact_lead_ids = set()
        if ext_member_ids:
            member_sessions = QwSession.objects.filter(
                session_type='contact',
                external_id__in=ext_member_ids,
            )
            via_contact_lead_ids = set(
                LeadSessionBind.objects.filter(session__in=member_sessions)
                .values_list('lead_id', flat=True)
            )

        all_m1_ids = direct_bound_ids | via_contact_lead_ids
        m1_leads = _serialize_leads(
            CrmLeads.objects.using('crm').filter(id__in=all_m1_ids, is_deleted=0)
        ) if all_m1_ids else []

        # 群 M2：不做（群本身没有联系人信息做模糊匹配）
        return JsonResponse({
            'session_id': session.id,
            'session_type': 'group',
            'contact': {
                'name': group_name,
                'type': 0,
                'mobile': '',
                'corp_name': '',
                'chat_id': chat_id,
                'member_count': len(member_list),
                'ext_member_count': len(ext_member_ids),
            },
            'm1_leads': m1_leads,
            'm2_leads': [],
            'match_by': 'group_member_sessions' if via_contact_lead_ids else '',
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


@csrf_exempt
def api_lead_bind(request):
    """
    POST /api/lead/bind
    将线索绑定到会话（或解除绑定）。
    Body JSON: { session_id, lead_id, userid, action: "bind"|"unbind" }
    权限：只允许绑定自己负责的线索（owner_primary == 自己的 crm_user_id），超管不限。
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'method not allowed'}, status=405)

    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': '无效的 JSON'}, status=400)

    session_id = body.get('session_id')
    lead_id = body.get('lead_id')
    userid = body.get('userid', '')
    action = body.get('action', 'bind')

    if not session_id or not lead_id or not userid:
        return JsonResponse({'error': '缺少参数'}, status=400)

    # 取会话
    try:
        session = QwSession.objects.get(id=session_id)
    except QwSession.DoesNotExist:
        return JsonResponse({'error': '会话不存在'}, status=404)

    # 取线索（用 crm 库）
    try:
        lead = CrmLeads.objects.using('crm').get(id=lead_id, is_deleted=0)
    except CrmLeads.DoesNotExist:
        return JsonResponse({'error': '线索不存在'}, status=404)

    # 权限校验：只能绑定自己负责的线索（超管不限）
    if userid not in SUPER_USERS:
        try:
            ui = UserInfo.objects.get(qw_id=userid)
        except UserInfo.DoesNotExist:
            return JsonResponse({'error': '未找到该用户'}, status=403)
        if lead.owner_primary != ui.crm_user_id:
            return JsonResponse({'error': '只能绑定自己负责的线索'}, status=403)

    if action == 'unbind':
        LeadSessionBind.objects.filter(session=session, lead_id=lead_id).delete()
        return JsonResponse({'ok': True, 'action': 'unbind'})

    # bind（幂等）
    bind_type = body.get('bind_type', 'manual')
    obj, created = LeadSessionBind.objects.get_or_create(
        session=session,
        lead_id=lead_id,
        defaults={
            'lead_crm_id': lead.crm_id or '',
            'bind_type': bind_type,
            'bound_by': userid,
        }
    )
    return JsonResponse({'ok': True, 'action': 'bind', 'created': created})


def api_lead_bindable(request):
    """
    GET /api/lead/bindable?userid=&session_id=
    返回该销售自己负责的线索（用于 M3 下拉），排除已绑定到本会话的。
    """
    userid = request.GET.get('userid', '')
    session_id = request.GET.get('session_id', '')

    if not userid:
        return JsonResponse({'error': '缺少 userid'}, status=400)

    # 只取自己负责的（crm_user_id），超管也只看自己（避免下拉过长）
    try:
        ui = UserInfo.objects.get(qw_id=userid)
        own_crm_id = ui.crm_user_id or ''
    except UserInfo.DoesNotExist:
        return JsonResponse({'error': '未找到该用户'}, status=404)

    if not own_crm_id:
        return JsonResponse({'leads': [], 'total': 0})

    qs = CrmLeads.objects.using('crm').filter(owner_primary=own_crm_id, is_deleted=0)

    # 排除已绑定到本会话的
    if session_id:
        try:
            session = QwSession.objects.get(id=session_id)
            already_bound = set(
                LeadSessionBind.objects.filter(session=session).values_list('lead_id', flat=True)
            )
            if already_bound:
                qs = qs.exclude(id__in=already_bound)
        except QwSession.DoesNotExist:
            pass

    leads = list(qs.order_by('-row_updated_at')[:100].values(
        'id', 'name', 'company', 'mobile', 'biz_status_label', 'owner_primary',
    ))
    for lead in leads:
        for k, v in lead.items():
            if hasattr(v, 'isoformat'):
                lead[k] = v.isoformat()

    return JsonResponse({'leads': leads, 'total': len(leads)})
