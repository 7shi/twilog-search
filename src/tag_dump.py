#!/usr/bin/env python3
"""
タグデータをbatch/results.jsonlから抽出し、batch/tags.yamlに出力する。
"""

import yaml
from pathlib import Path
from batch_reader import BatchReader

def main():
    """
    batch/results.jsonlからタグデータを抽出し、2つの形式で出力する。
    1. batch/tags.tsv: 投稿→タグ形式
    2. batch/tags.txt: タグ一覧
    """
    results_path = Path("batch/results.jsonl")
    posts_tags_path = Path("batch/tags.tsv")
    tags_list_path = Path("batch/tags.txt")
    
    if not results_path.exists():
        print(f"エラー: {results_path} が見つかりません")
        return
    
    print("タグデータを抽出中...")
    reader = BatchReader(results_path)
    reader.initialize()
    
    print("タグデータを処理中...")
    posts_tags = {}
    all_tags = set()
    max_tags = 0
    
    for post_id, summary_data in reader.summaries_data.items():
        tags = summary_data.get("tags", [])
        posts_tags[post_id] = tags
        all_tags.update(tags)
        max_tags = max(max_tags, len(tags))
    
    # TSV形式で出力
    print(f"最大タグ数: {max_tags}")
    print(f"TSV形式で出力中: {posts_tags_path}")
    
    with open(posts_tags_path, 'w', encoding='utf-8') as f:
        # ヘッダー行を出力
        header = ["post_id"] + [f"tag{i+1}" for i in range(max_tags)]
        f.write('\t'.join(header) + '\n')
        
        # データ行を出力（タグがある投稿のみ）
        for post_id in sorted(posts_tags.keys()):
            tags = posts_tags[post_id]
            if tags:  # タグがある場合のみ出力
                tags_str = '\t'.join(tags)
                f.write(f"{post_id}\t{tags_str}\n")
    
    # タグ一覧を出力
    print(f"タグ一覧を出力中: {tags_list_path}")
    sorted_tags = sorted(list(all_tags))
    
    with open(tags_list_path, 'w', encoding='utf-8') as f:
        for tag in sorted_tags:
            f.write(f"{tag}\n")
    
    print(f"完了:")
    print(f"  TSV: {len(posts_tags)} 件の投稿のタグデータ ({posts_tags_path.stat().st_size:,} バイト)")
    print(f"  一覧: {len(sorted_tags)} 個のユニークなタグ ({tags_list_path.stat().st_size:,} バイト)")

if __name__ == "__main__":
    main()