#!/usr/bin/env python3
"""Patch chat.py to add workspace_id-based search scoping."""
import re

path = "/Users/hyun/Dev/nalutbae/mai-brain/backend/app/api/chat.py"
with open(path, "r") as f:
    content = f.read()

# Insert collection-name resolution between session creation and hybrid_search
old_block = '''    # 2. 하이브리드 검색
    try:
        search_result = hybrid_search(
            query=request.question,
            mode=request.mode,
            session_id=session_id,
        )'''

new_block = '''    # 1.5 워크스페이스 컬렉션 결정
    collection_name = None
    if request.workspace_id:
        from app.core.workspace import get_workspace_store
        ws_store = get_workspace_store()
        collection_name = ws_store.get_collection_name(request.workspace_id)
        logger.info("워크스페이스 검색: workspace_id=%s, collection=%s",
                     request.workspace_id, collection_name)

    # 2. 하이브리드 검색
    try:
        search_result = hybrid_search(
            query=request.question,
            mode=request.mode,
            session_id=session_id,
            collection_name=collection_name,
        )'''

if old_block in content:
    content = content.replace(old_block, new_block)
    with open(path, "w") as f:
        f.write(content)
    print("PATCHED: chat.py — added workspace collection_name scoping")
else:
    print("FAILED: old_block not found in chat.py")
    # Check if already patched
    if "collection_name=collection_name" in content:
        print("Already patched — collection_name already present")
    else:
        print("Block not found. Checking for partial match...")
        if "workspace_id" in content and "collection_name" in content:
            print("Both workspace_id and collection_name present — may already be patched")
