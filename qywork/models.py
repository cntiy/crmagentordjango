from django.db import models


class UserInfo(models.Model):
    """员工信息表（企微 qw_id 对应 OAuth userid）"""
    qw_id = models.CharField(primary_key=True, max_length=40)
    name = models.CharField(max_length=50, blank=True, null=True)
    department = models.CharField(max_length=50, blank=True, null=True)
    crm_user_id = models.CharField(max_length=10, blank=True, null=True)
    position = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'user_info'


class CrmLeads(models.Model):
    """线索主表"""
    id = models.BigAutoField(primary_key=True)
    crm_id = models.CharField(unique=True, max_length=64)
    name = models.CharField(max_length=255, blank=True, null=True, verbose_name='姓名')
    mobile = models.CharField(max_length=255, blank=True, null=True, verbose_name='手机')
    tel = models.CharField(max_length=255, blank=True, null=True, verbose_name='电话')
    email = models.CharField(max_length=255, blank=True, null=True)
    wechat_id = models.CharField(max_length=128, blank=True, null=True)
    wechat_nickname = models.CharField(max_length=255, blank=True, null=True)
    company = models.CharField(max_length=255, blank=True, null=True, verbose_name='公司全称')
    department = models.CharField(max_length=255, blank=True, null=True)
    job_title = models.CharField(max_length=255, blank=True, null=True)
    address = models.CharField(max_length=1024, blank=True, null=True, verbose_name='地址')
    leads_stage = models.CharField(max_length=64, blank=True, null=True)
    leads_stage_label = models.CharField(max_length=64, blank=True, null=True, verbose_name='线索阶段')
    life_status = models.CharField(max_length=64, blank=True, null=True)
    life_status_label = models.CharField(max_length=64, blank=True, null=True, verbose_name='生命状态')
    biz_status = models.CharField(max_length=64, blank=True, null=True)
    biz_status_label = models.CharField(max_length=64, blank=True, null=True, verbose_name='业务状态')
    lock_status = models.CharField(max_length=64, blank=True, null=True)
    lock_status_label = models.CharField(max_length=64, blank=True, null=True, verbose_name='锁定状态')
    record_type = models.CharField(max_length=64, blank=True, null=True)
    record_type_label = models.CharField(max_length=64, blank=True, null=True, verbose_name='业务类型')
    origin_source = models.CharField(max_length=64, blank=True, null=True)
    origin_source_label = models.CharField(max_length=64, blank=True, null=True, verbose_name='来源系统')
    source = models.CharField(max_length=64, blank=True, null=True)
    source_label = models.CharField(max_length=64, blank=True, null=True, verbose_name='来源细分')
    promotion_channel = models.CharField(max_length=64, blank=True, null=True)
    promotion_channel_label = models.CharField(max_length=64, blank=True, null=True, verbose_name='推广渠道')
    terminal_customer_name = models.CharField(max_length=255, blank=True, null=True, verbose_name='终端客户名称')
    terminal_customer_type = models.CharField(max_length=64, blank=True, null=True)
    terminal_customer_type_label = models.CharField(max_length=64, blank=True, null=True, verbose_name='终端客户类型')
    terminal_customer_location = models.CharField(max_length=255, blank=True, null=True, verbose_name='终端客户所在地')
    terminal_industry = models.CharField(max_length=128, blank=True, null=True)
    terminal_industry_label = models.CharField(max_length=128, blank=True, null=True, verbose_name='终端行业')
    terminal_main_business = models.TextField(blank=True, null=True, verbose_name='终端客户主营业务')
    terminal_register_capital = models.CharField(max_length=64, blank=True, null=True, verbose_name='终端注册资本')
    terminal_paid_capital = models.CharField(max_length=64, blank=True, null=True, verbose_name='终端实缴资本')
    terminal_employee_count = models.CharField(max_length=64, blank=True, null=True, verbose_name='终端参保人数')
    terminal_company_found_time = models.CharField(max_length=32, blank=True, null=True, verbose_name='终端公司成立时间')
    product_brand = models.CharField(max_length=128, blank=True, null=True)
    product_brand_label = models.CharField(max_length=128, blank=True, null=True, verbose_name='指定品牌')
    product_model = models.JSONField(blank=True, null=True)
    product_model_label = models.JSONField(blank=True, null=True, verbose_name='产品型号')
    product_spec = models.CharField(max_length=255, blank=True, null=True, verbose_name='产品规格')
    product_category = models.JSONField(blank=True, null=True)
    product_category_label = models.JSONField(blank=True, null=True, verbose_name='产品品类')
    product_function = models.JSONField(blank=True, null=True)
    product_function_label = models.JSONField(blank=True, null=True, verbose_name='产品功能')
    industry = models.CharField(max_length=128, blank=True, null=True)
    industry_label = models.CharField(max_length=128, blank=True, null=True, verbose_name='渠道行业')
    industry_other = models.CharField(max_length=128, blank=True, null=True)
    industry_other_label = models.CharField(max_length=128, blank=True, null=True)
    industry_channel = models.CharField(max_length=128, blank=True, null=True)
    industry_channel_label = models.CharField(max_length=128, blank=True, null=True)
    industry_status = models.CharField(max_length=64, blank=True, null=True)
    industry_status_label = models.CharField(max_length=64, blank=True, null=True, verbose_name='行业地位')
    industry_ext = models.TextField(blank=True, null=True, verbose_name='行业延展')
    main_business = models.TextField(blank=True, null=True, verbose_name='主营业务')
    business_scope = models.TextField(blank=True, null=True, verbose_name='经营范围')
    customer_scale = models.CharField(max_length=64, blank=True, null=True, verbose_name='客户规模')
    customer_quality = models.CharField(max_length=64, blank=True, null=True)
    customer_quality_label = models.CharField(max_length=64, blank=True, null=True, verbose_name='客户质量')
    customer_stage = models.CharField(max_length=64, blank=True, null=True)
    customer_stage_label = models.CharField(max_length=64, blank=True, null=True, verbose_name='客户阶段')
    customer_type = models.CharField(max_length=64, blank=True, null=True)
    customer_type_label = models.CharField(max_length=64, blank=True, null=True, verbose_name='客户类型')
    main_market = models.TextField(blank=True, null=True, verbose_name='主要市场及主要客户')
    register_capital = models.CharField(max_length=64, blank=True, null=True, verbose_name='注册资本')
    register_capital_wan = models.DecimalField(max_digits=20, decimal_places=4, blank=True, null=True, verbose_name='注册资本(万元)')
    paid_capital = models.CharField(max_length=64, blank=True, null=True, verbose_name='实缴资本')
    paid_capital_num = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    capital_nature = models.CharField(max_length=64, blank=True, null=True)
    capital_nature_label = models.CharField(max_length=64, blank=True, null=True, verbose_name='资本性质')
    first_deal_amount = models.DecimalField(max_digits=20, decimal_places=4, blank=True, null=True, verbose_name='首次成交金额')
    first_deal_amount_2 = models.DecimalField(max_digits=20, decimal_places=4, blank=True, null=True)
    first_deal_time = models.DateTimeField(blank=True, null=True, verbose_name='首次成交时间')
    deal_cycle = models.DecimalField(max_digits=10, decimal_places=4, blank=True, null=True, verbose_name='成交周期')
    owner = models.JSONField(blank=True, null=True, verbose_name='负责人')
    owner_primary = models.CharField(max_length=10, blank=True, null=True, verbose_name='主负责人CRM ID')
    created_by = models.JSONField(blank=True, null=True, verbose_name='创建者')
    last_modified_by = models.JSONField(blank=True, null=True, verbose_name='最后修改者')
    last_follower = models.JSONField(blank=True, null=True, verbose_name='最后跟进者')
    assigner_id = models.JSONField(blank=True, null=True, verbose_name='分配者')
    lock_user = models.JSONField(blank=True, null=True, verbose_name='锁定者')
    out_owner = models.JSONField(blank=True, null=True, verbose_name='外部负责人')
    relevant_team = models.JSONField(blank=True, null=True, verbose_name='协作团队')
    create_time = models.DateTimeField(blank=True, null=True, verbose_name='CRM创建时间')
    last_modified_time = models.DateTimeField(blank=True, null=True, verbose_name='CRM最后修改时间')
    last_follow_time = models.DateTimeField(blank=True, null=True, verbose_name='最后跟进时间')
    next_followed_time = models.DateTimeField(blank=True, null=True, verbose_name='下次跟进时间')
    assigned_time = models.DateTimeField(blank=True, null=True, verbose_name='领取/分配时间')
    expire_time = models.DateTimeField(blank=True, null=True, verbose_name='预计回收时间')
    returned_time = models.DateTimeField(blank=True, null=True, verbose_name='退回/回收时间')
    transform_time = models.DateTimeField(blank=True, null=True, verbose_name='转化时间')
    owner_change_time = models.DateTimeField(blank=True, null=True, verbose_name='负责人变更时间')
    leads_stage_changed_time = models.DateTimeField(blank=True, null=True, verbose_name='线索阶段变更时间')
    gender = models.CharField(max_length=16, blank=True, null=True)
    gender_label = models.CharField(max_length=16, blank=True, null=True, verbose_name='性别')
    last_year_revenue = models.DecimalField(max_digits=20, decimal_places=4, blank=True, null=True, verbose_name='去年营收(亿)')
    last_year_profit = models.DecimalField(max_digits=20, decimal_places=4, blank=True, null=True, verbose_name='去年净利润')
    company_found_date = models.DateField(blank=True, null=True, verbose_name='企业成立时间')
    employee_count = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True, verbose_name='参保人数')
    production_base_info = models.TextField(blank=True, null=True, verbose_name='生产基地信息')
    investment_plan = models.TextField(blank=True, null=True, verbose_name='投资计划')
    history_record = models.CharField(max_length=64, blank=True, null=True)
    history_record_label = models.CharField(max_length=64, blank=True, null=True, verbose_name='历史记录')
    leads_pool_id_ref = models.CharField(max_length=64, blank=True, null=True)
    url = models.CharField(max_length=512, blank=True, null=True)
    remark = models.TextField(blank=True, null=True, verbose_name='备注')
    attachments = models.JSONField(blank=True, null=True)
    qixinbao_url = models.TextField(blank=True, null=True)
    historical_pool_customer = models.CharField(max_length=255, blank=True, null=True)
    history_lead_info = models.CharField(max_length=255, blank=True, null=True)
    history_follower_ref = models.CharField(max_length=255, blank=True, null=True)
    reassigned_to = models.CharField(max_length=255, blank=True, null=True)
    raw_json = models.JSONField(blank=True, null=True)
    is_deleted = models.IntegerField(default=0)
    last_synced_at = models.DateTimeField(blank=True, null=True)
    row_created_at = models.DateTimeField()
    row_updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'crm_leads'
        verbose_name = '线索'
        verbose_name_plural = '线索列表'
        ordering = ['-row_updated_at']


class CrmFieldMapping(models.Model):
    """CRM字段映射元数据"""
    object_api = models.CharField(max_length=64)
    api_name = models.CharField(max_length=128)
    label = models.CharField(max_length=128, blank=True, null=True, verbose_name='字段标签')
    db_column = models.CharField(max_length=64, blank=True, null=True)
    db_column_label = models.CharField(max_length=64, blank=True, null=True)
    field_type = models.CharField(max_length=32, blank=True, null=True)
    data_type = models.CharField(max_length=32, blank=True, null=True)
    is_editable = models.IntegerField()
    is_required = models.IntegerField()
    remark = models.CharField(max_length=255, blank=True, null=True)
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'crm_field_mapping'


class SyncLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    object_api = models.CharField(max_length=64)
    mode = models.CharField(max_length=16)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField(blank=True, null=True)
    since = models.DateTimeField(blank=True, null=True)
    until = models.DateTimeField(blank=True, null=True)
    fetched = models.IntegerField()
    inserted = models.IntegerField()
    updated = models.IntegerField()
    marked_deleted = models.IntegerField()
    status = models.CharField(max_length=16)
    error_msg = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'sync_log'


class SyncWatermark(models.Model):
    object_api = models.CharField(primary_key=True, max_length=64)
    last_modified_time = models.DateTimeField(blank=True, null=True)
    last_full_sync_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'sync_watermark'
