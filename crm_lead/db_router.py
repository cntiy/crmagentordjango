"""
数据库路由：
  - qywork app 下的所有 model 都走 `crm` 库（业务 MySQL）
  - Django 内置 app（auth/admin/sessions/contenttypes/...）继续走 default(SQLite)
  - 迁移规则：qywork 中 managed=True 的 model 才迁移到 crm 库；
    managed=False 的（crm_leads/user_info 等由外部 sync 任务维护）跳过。
"""

from django.apps import apps

CRM_APP = "qywork"
CRM_DB = "crm"


class CrmRouter:
    def db_for_read(self, model, **hints):
        if model._meta.app_label == CRM_APP:
            return CRM_DB
        return None

    def db_for_write(self, model, **hints):
        if model._meta.app_label == CRM_APP:
            return CRM_DB
        return None

    def allow_relation(self, obj1, obj2, **hints):
        return obj1._state.db == obj2._state.db

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label == CRM_APP:
            if db != CRM_DB:
                return False
            if model_name is None:
                return True
            try:
                model = apps.get_model(app_label, model_name)
            except LookupError:
                return False
            return model._meta.managed
        return db == "default"
