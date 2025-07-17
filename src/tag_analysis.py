#!/usr/bin/env python3

import csv
from collections import Counter
from pathlib import Path
import sys
import unicodedata
import math

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

def load_tag_data(tsv_file: str) -> Counter:
    """TSVファイルからタグデータを読み込み、出現回数をカウントする"""
    tag_counter = Counter()
    
    with open(tsv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            # post_id以外の全カラムからタグを取得
            for key, value in row.items():
                if key != 'post_id' and value and value.strip():
                    tag_counter[value.strip()] += 1
    
    return tag_counter

def display_top_tags(tag_counter: Counter, top_n: int = 20):
    """最頻出N個のタグを表示"""
    print(f"最頻出{top_n}タグ:")
    print("-" * 40)
    
    for i, (tag, count) in enumerate(tag_counter.most_common(top_n), 1):
        formatted_tag = format_with_width(tag, 20)
        print(f"{i:2d}. {formatted_tag} {count:>7,}回")

def display_statistics(tag_counter: Counter):
    """タグ統計情報を表示"""
    total_unique_tags = len(tag_counter)
    total_tag_occurrences = sum(tag_counter.values())
    max_count = max(tag_counter.values()) if tag_counter else 0
    
    print(f"\nタグ統計情報:")
    print("-" * 40)
    print(f"総タグ数（ユニーク）: {total_unique_tags:,}")
    print(f"総タグ出現回数: {total_tag_occurrences:,}")
    print(f"最大出現回数: {max_count:,}")
    
    # 順位別出現回数を表示
    print(f"\n順位別出現回数:")
    print("-" * 40)
    most_common = tag_counter.most_common()
    positions = [10, 20, 50, 100]
    
    for pos in positions:
        if pos <= len(most_common):
            tag, count = most_common[pos - 1]  # 0-indexedなので-1
            print(f"{pos:3d}位: {count:>6,}回 ({tag})")
        else:
            print(f"{pos:3d}位: データなし")

def display_histogram(tag_counter: Counter):
    """全タグの出現数分布をヒストグラム表示（対数スケール）"""
    print(f"\nタグ出現数分布ヒストグラム (対数スケール):")
    print("-" * 80)
    
    if not tag_counter:
        return
    
    # 出現数を区間で集計
    counts = list(tag_counter.values())
    max_count = max(counts)
    
    bins = {}
    for count in counts:
        if count < 1000:
            # 1000未満は100刻み
            bin_key = (count // 100) * 100
        else:
            # 1000以上は1000刻み
            bin_key = (count // 1000) * 1000
        bins[bin_key] = bins.get(bin_key, 0) + 1
    
    # ソートして表示
    sorted_bins = sorted(bins.items())
    max_bar_width = 50
    
    for bin_start, tag_count in sorted_bins:
        if bin_start < 1000:
            bin_end = bin_start + 99
            if bin_start == 0:
                bin_start = 1  # 1-99として表示
        else:
            bin_end = bin_start + 999
        
        # 対数スケールで棒グラフの長さを決定
        log_value = math.log10(tag_count) if tag_count > 0 else 0
        max_log = math.log10(max(bins.values()))
        bar_width = int((log_value / max_log) * max_bar_width) if max_log > 0 else 0
        # 棒の長さが0でなければ最低1にする
        if tag_count > 0 and bar_width == 0:
            bar_width = 1
        bar = "█" * bar_width
        
        bin_label = f"{bin_start:6,}-{bin_end:6,}"
        print(f"{bin_label}: {tag_count:>6,}タグ |{bar}")
    
    print(f"\n最大出現回数: {max_count:,}回")
    print(f"総タグ数: {len(tag_counter):,}個")

def main():
    tsv_file = "batch/tags.tsv"
    
    if not Path(tsv_file).exists():
        print(f"エラー: {tsv_file} が見つかりません", file=sys.stderr)
        sys.exit(1)
    
    try:
        tag_counter = load_tag_data(tsv_file)
        
        if not tag_counter:
            print("タグデータが見つかりませんでした", file=sys.stderr)
            sys.exit(1)
        
        display_top_tags(tag_counter)
        display_statistics(tag_counter)
        display_histogram(tag_counter)
        
    except Exception as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()