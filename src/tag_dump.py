#!/usr/bin/env python3
"""
タグデータをbatch/results.jsonlから抽出し、batch/tags.yamlに出力する。
"""

import yaml
from pathlib import Path
from batch_reader import BatchReader

def extract_tags_from_results():
    """
    batch/results.jsonlからタグデータを抽出し、batch/tags.tsvに出力する。
    
    出力形式:
    post_id	tag1	tag2	...
    """
    results_path = Path("batch/results.jsonl")
    posts_tags_path = Path("batch/tags.tsv")
    
    if not results_path.exists():
        print(f"エラー: {results_path} が見つかりません")
        return
    
    print("タグデータを抽出中...")
    reader = BatchReader(results_path)
    reader.initialize()
    
    print("最大タグ数を調査中...")
    posts_tags = {}
    max_tags = 0
    for post_id, summary_data in reader.summaries_data.items():
        tags = summary_data.get("tags", [])
        posts_tags[post_id] = tags
        max_tags = max(max_tags, len(tags))
    
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
    
    print(f"完了: {len(posts_tags)} 件の投稿のタグデータを出力しました")
    print(f"ファイルサイズ: {posts_tags_path.stat().st_size:,} バイト")

if __name__ == "__main__":
    extract_tags_from_results()