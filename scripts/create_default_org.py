"""创建系统用户和默认组织 — 幂等脚本，重复执行安全"""

from __future__ import annotations

import asyncio
import logging
import secrets
import sys

from src.storage.pg_store import PgStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SYSTEM_USER_ID = "usr_system"
SYSTEM_USERNAME = "system"
DEFAULT_ORG_ID = "org_default"
DEFAULT_ORG_NAME = "default"
DEFAULT_ORG_DESC = "默认组织（存量数据）"


async def main():
    pg = PgStore()

    # 1. 创建系统用户（幂等：已存在则跳过）
    existing_user = await pg.get_user_by_username(SYSTEM_USERNAME)
    if existing_user:
        logger.info("系统用户 '%s' 已存在，跳过", SYSTEM_USERNAME)
    else:
        random_pw = secrets.token_urlsafe(32)
        from src.api.auth_utils import hash_password

        pw_hash = hash_password(random_pw)
        await pg.create_user(
            user_id=SYSTEM_USER_ID,
            username=SYSTEM_USERNAME,
            password_hash=pw_hash,
            display_name="系统管理员",
        )
        logger.info("系统用户 '%s' 创建成功，随机密码: %s", SYSTEM_USERNAME, random_pw)
        logger.warning("请妥善保存上述密码，该密码不会再次输出")

    # 2. 创建默认组织（幂等：已存在则跳过）
    existing_org = await pg.get_organization_by_name(DEFAULT_ORG_NAME)
    if existing_org:
        logger.info("默认组织 '%s' 已存在，跳过", DEFAULT_ORG_NAME)
    else:
        await pg.create_organization(
            org_id=DEFAULT_ORG_ID,
            name=DEFAULT_ORG_NAME,
            description=DEFAULT_ORG_DESC,
            created_by=SYSTEM_USER_ID,
        )
        logger.info("默认组织 '%s' 创建成功", DEFAULT_ORG_NAME)

    # 3. 将系统用户加入默认组织（幂等：已是成员则跳过）
    membership = await pg.get_membership(DEFAULT_ORG_ID, SYSTEM_USER_ID)
    if membership:
        logger.info("系统用户已是默认组织成员，跳过")
    else:
        await pg.create_membership(
            membership_id="mem_system_default",
            org_id=DEFAULT_ORG_ID,
            user_id=SYSTEM_USER_ID,
            role="admin",
        )
        logger.info("系统用户已加入默认组织（admin）")

    logger.info("初始化完成")
    logger.info("默认组织 ID: %s", DEFAULT_ORG_ID)


if __name__ == "__main__":
    asyncio.run(main())
