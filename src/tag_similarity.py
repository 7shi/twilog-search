#!/usr/bin/env python3

from collections import Counter
from pathlib import Path
import sys
import unicodedata
from tag_reader import TagReader

def get_display_width(text: str) -> int:
    """文字列の表示幅を取得（全角文字は2、半角文字は1として計算）"""
    width = 0
    for char in text:
        if unicodedata.east_asian_width(char) in ('F', 'W'):
            width += 2  # 全角文字
        else:
            width += 1  # 半角文字
    return width

def format_with_width(text: str, width: int, align: str = 'left') -> str:
    """表示幅を考慮した文字列整形"""
    current_width = get_display_width(text)
    padding = width - current_width
    
    if padding <= 0:
        return text
    
    if align == 'right':
        return ' ' * padding + text
    else:  # left
        return text + ' ' * padding

def load_tag_data_from_reader(reader: TagReader) -> Counter:
    """TagReaderからタグデータを読み込み、出現回数をカウントする"""
    tag_counter = Counter()
    
    # 各投稿のタグを集計
    for entry in reader.tag_data:
        for tag in entry['tags']:
            tag_counter[tag] += 1
    
    return tag_counter


def find_similar_tags(reader: TagReader, target_tag: str, top_k: int = 12) -> list:
    """指定されたタグに類似するタグを検索（TagReaderのsearch_similar_tagsを使用）"""
    target_vector = reader.get_tag_vector(target_tag)
    if target_vector is None:
        return []
    
    # TagReaderの既存メソッドを使用
    results = reader.search_similar_tags(target_vector, top_k)
    
    # 対象タグ自体を除外
    filtered_results = []
    for tag, score in results:
        if tag != target_tag:
            filtered_results.append((tag, score))
    
    return filtered_results

def display_tag_similarities(reader: TagReader, tag_counter: Counter, top_n: int = 30):
    """出現数上位のタグについて、類似タグを表示"""
    print(f"\n出現数上位{top_n}タグの類似タグ分析（コサイン類似度上位12個）:")
    print("-" * 100)
    
    # 上位タグを取得
    top_tags = tag_counter.most_common(top_n)
    
    # 最大表示幅を計算
    max_width = 0
    for tag, _ in top_tags:
        width = get_display_width(tag)
        max_width = max(max_width, width)
    
    for i, (tag, count) in enumerate(top_tags, 1):
        # 類似タグを検索
        try:
            similar_tags = find_similar_tags(reader, tag, top_k=12)
        except Exception as e:
            print(f"エラー（{tag}）: {e}", file=sys.stderr)
            similar_tags = []
        
        # 最初の行の構成要素
        formatted_tag = format_with_width(tag, max_width)
        first_line = f"{i:2d}. {formatted_tag} {count:>7,}回"
        
        # 2行目以降の開始位置を計算
        indent = len(f"{i:2d}. ") + max_width + len(f" {count:>7,}回 ")
        indent_str = " " * (indent + 1)
        
        # 類似タグを4個ずつ3行に分けて表示
        if similar_tags:
            # 類似度付きタグのフォーマット
            similar_tags_formatted = []
            for similar_tag, similarity in similar_tags:
                similar_tags_formatted.append(f"{similar_tag}({similarity:.3f})")
            
            # 1行目：基本情報 + 類似タグ1-4
            line1_tags = " ".join(similar_tags_formatted[:4])
            print(f"{first_line} {line1_tags}")
            
            # 2行目：類似タグ5-8
            if len(similar_tags_formatted) > 4:
                line2_tags = " ".join(similar_tags_formatted[4:8])
                print(f"{indent_str}{line2_tags}")
            
            # 3行目：類似タグ9-12
            if len(similar_tags_formatted) > 8:
                line3_tags = " ".join(similar_tags_formatted[8:12])
                print(f"{indent_str}{line3_tags}")
        else:
            print(f"{first_line} 類似タグなし")

def main():
    try:
        # TagReaderを使用してデータを読み込み（ベクトル必要）
        reader = TagReader(load_vectors=True)
        
        if not reader.is_data_loaded()['tsv']:
            print("タグデータが見つかりませんでした", file=sys.stderr)
            sys.exit(1)
        
        if not reader.is_data_loaded()['safetensors']:
            print("タグベクトルが見つかりませんでした", file=sys.stderr)
            sys.exit(1)
        
        # タグ出現数を取得
        tag_counter = load_tag_data_from_reader(reader)
        
        if not tag_counter:
            print("タグデータが見つかりませんでした", file=sys.stderr)
            sys.exit(1)
        
        # 類似タグ分析を実行
        display_tag_similarities(reader, tag_counter)
        
    except Exception as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()