"""Milvus Collection 初始化脚本"""

import logging

logging.basicConfig(level=logging.INFO)

from src.storage.milvus_store import MilvusStore


def main():
    store = MilvusStore()
    store.init_collection()
    print("Milvus Collection 初始化完成")


if __name__ == "__main__":
    main()
