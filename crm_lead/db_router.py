"""
数据库路由：
  - qywork app 下的所有 model 都走 `crm` 库（业务 MySQL）
  - Django 内置 app（auth/admin/sessions/contenttypes/...）继续走 default(SQLite)
"""

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
        # 同库内允许，跨库不允许
        return obj1._state.db == obj2._state.db

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        # qywork 表是 managed=False，不应该 migrate；其他 app 只在 default 库迁移
        if app_label == CRM_APP:
            return False
        return db == "default"
