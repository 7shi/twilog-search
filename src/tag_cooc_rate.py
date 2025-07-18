#!/usr/bin/env python3

from collections import Counter, defaultdict
from pathlib import Path
import sys
import unicodedata
import math
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

def load_tag_data_from_reader(reader: TagReader) -> tuple[Counter, dict]:
    """TagReaderからタグデータを読み込み、出現回数と共起数をカウントする"""
    tag_counter = Counter()
    cooc_counter = defaultdict(Counter)
    
    # 各投稿のタグを集計
    for entry in reader.tag_data:
        tags = entry['tags']
        
        # 個別タグの出現回数をカウント
        for tag in tags:
            tag_counter[tag] += 1
        
        # 共起関係をカウント（同じ投稿内のタグペア）
        for i, tag_a in enumerate(tags):
            for j, tag_b in enumerate(tags):
                if i != j:  # 自分自身は除く
                    cooc_counter[tag_a][tag_b] += 1
    
    return tag_counter, cooc_counter

def collect_cooc_rates(tag_counter: Counter, cooc_counter: dict, top_n: int = 100) -> list[float]:
    """上位N個のタグについて、全ての共起率を収集"""
    all_cooc_rates = []
    
    # 上位タグを取得
    top_tags = [tag for tag, _ in tag_counter.most_common(top_n)]
    
    for tag in top_tags:
        if tag not in cooc_counter:
            continue
            
        tag_count = tag_counter[tag]
        if tag_count == 0:
            continue
        
        # このタグの全共起関係について共起率を計算
        for other_tag, cooc_count in cooc_counter[tag].items():
            rate = cooc_count / tag_count
            all_cooc_rates.append(rate)
    
    return all_cooc_rates

def calculate_cooc_rates(tag_counter: Counter, cooc_counter: dict, target_tag: str) -> list:
    """指定されたタグに対する共起率を計算"""
    if target_tag not in cooc_counter:
        return []
    
    target_count = tag_counter[target_tag]
    if target_count == 0:
        return []
    
    cooc_rates = []
    for other_tag, cooc_count in cooc_counter[target_tag].items():
        rate = cooc_count / target_count
        cooc_rates.append((other_tag, rate, cooc_count))
    
    # 共起率の降順でソート
    cooc_rates.sort(key=lambda x: x[1], reverse=True)
    
    return cooc_rates

def display_tag_cooc_rates(reader: TagReader, tag_counter: Counter, cooc_counter: dict, top_n: int = 30):
    """出現数上位のタグについて、共起率を表示"""
    print(f"出現数上位{top_n}タグの共起率分析（共起率上位12個）:")
    print("-" * 100)
    
    # 上位タグを取得
    top_tags = tag_counter.most_common(top_n)
    
    # 最大表示幅を計算
    max_width = 0
    for tag, _ in top_tags:
        width = get_display_width(tag)
        max_width = max(max_width, width)
    
    for i, (tag, count) in enumerate(top_tags, 1):
        # 共起率を計算
        try:
            cooc_rates = calculate_cooc_rates(tag_counter, cooc_counter, tag)
            # 上位12個に限定
            cooc_rates = cooc_rates[:12]
        except Exception as e:
            print(f"エラー（{tag}）: {e}", file=sys.stderr)
            cooc_rates = []
        
        # 最初の行の構成要素
        formatted_tag = format_with_width(tag, max_width)
        first_line = f"{i:2d}. {formatted_tag} {count:>7,}回"
        
        # 2行目以降の開始位置を計算
        indent = len(f"{i:2d}. ") + max_width + len(f" {count:>7,}回 ")
        indent_str = " " * (indent + 1)
        
        # 共起率付きタグを4個ずつ3行に分けて表示
        if cooc_rates:
            # 共起率付きタグのフォーマット
            cooc_tags_formatted = []
            for other_tag, rate, cooc_count in cooc_rates:
                cooc_tags_formatted.append(f"{other_tag}({rate:.1%})")
            
            # 1行目：基本情報 + 共起率1-4
            line1_tags = " ".join(cooc_tags_formatted[:4])
            print(f"{first_line} {line1_tags}")
            
            # 2行目：共起率5-8
            if len(cooc_tags_formatted) > 4:
                line2_tags = " ".join(cooc_tags_formatted[4:8])
                print(f"{indent_str}{line2_tags}")
            
            # 3行目：共起率9-12
            if len(cooc_tags_formatted) > 8:
                line3_tags = " ".join(cooc_tags_formatted[8:12])
                print(f"{indent_str}{line3_tags}")
        else:
            print(f"{first_line} 共起タグなし")

def collect_cooc_rates_with_tags(tag_counter: Counter, cooc_counter: dict, top_n: int = 100) -> list[tuple[str, str, float]]:
    """上位N個のタグについて、全ての共起率をタグ名付きで収集"""
    all_cooc_rates = []
    
    # 上位タグを取得
    top_tags = [tag for tag, _ in tag_counter.most_common(top_n)]
    
    for tag in top_tags:
        if tag not in cooc_counter:
            continue
            
        tag_count = tag_counter[tag]
        if tag_count == 0:
            continue
        
        # このタグの全共起関係について共起率を計算
        for other_tag, cooc_count in cooc_counter[tag].items():
            rate = cooc_count / tag_count
            all_cooc_rates.append((tag, other_tag, rate))
    
    return all_cooc_rates

def display_top_cooc_rates(cooc_rates_with_tags: list[tuple[str, str, float]], top_n: int = 10):
    """共起率の上位を表示"""
    if not cooc_rates_with_tags:
        print("共起率データがありません")
        return
    
    print(f"\n共起率ベスト{top_n}:")
    print("-" * 70)
    
    # 共起率の降順でソート
    sorted_rates = sorted(cooc_rates_with_tags, key=lambda x: x[2], reverse=True)
    
    for i, (tag_a, tag_b, rate) in enumerate(sorted_rates[:top_n], 1):
        formatted_tag_a = format_with_width(tag_a, 15)
        formatted_tag_b = format_with_width(tag_b, 15)
        print(f"{i:2d}. {formatted_tag_a} → {formatted_tag_b} {rate:.1%}")

def display_cooc_rate_statistics(cooc_rates: list[float], top_n: int = 100):
    """共起率の統計情報を表示"""
    if not cooc_rates:
        print("共起率データがありません")
        return
    
    print(f"\n出現数上位{top_n}タグの共起率統計:")
    print("-" * 50)
    
    print(f"総共起関係数: {len(cooc_rates):,}")
    print(f"最大共起率: {max(cooc_rates):.1%}")
    print(f"最小共起率: {min(cooc_rates):.1%}")
    print(f"平均共起率: {sum(cooc_rates)/len(cooc_rates):.1%}")
    
    # 中央値を計算
    sorted_rates = sorted(cooc_rates)
    n = len(sorted_rates)
    if n % 2 == 0:
        median = (sorted_rates[n//2 - 1] + sorted_rates[n//2]) / 2
    else:
        median = sorted_rates[n//2]
    print(f"中央値: {median:.1%}")

def display_cooc_rate_histogram(cooc_rates: list[float], top_n: int = 100):
    """共起率のヒストグラムを表示（5%刻み、対数グラフ）"""
    if not cooc_rates:
        print("共起率データがありません")
        return
    
    print(f"\n出現数上位{top_n}タグの共起率分布ヒストグラム (5%刻み、対数グラフ):")
    print("-" * 80)
    
    # 5%刻みでビンを作成
    bins = {}
    for rate in cooc_rates:
        # 5%刻みの区間を決定（0-4.99%は0、5-9.99%は5、など）
        bin_key = int(rate * 100 // 5) * 5
        bins[bin_key] = bins.get(bin_key, 0) + 1
    
    # ソートして表示
    sorted_bins = sorted(bins.items())
    max_bar_width = 50
    
    import math
    max_count = max(bins.values()) if bins else 0
    max_log = math.log10(max_count) if max_count > 0 else 0
    
    for bin_start, count in sorted_bins:
        bin_end = bin_start + 4
        
        # 対数スケールで棒グラフの長さを決定
        if count > 0:
            log_value = math.log10(count)
            bar_width = int((log_value / max_log) * max_bar_width) if max_log > 0 else 0
        else:
            bar_width = 0
        
        # 0でなければ最低1にする
        if count > 0 and bar_width == 0:
            bar_width = 1
        
        bar = "█" * bar_width
        
        bin_label = f"{bin_start:2d}-{bin_end:2d}%"
        print(f"{bin_label}: {count:>7,}関係 |{bar}")
    
    print(f"\n総共起関係数: {len(cooc_rates):,}")

def main():
    try:
        # TagReaderを使用してデータを読み込み（ベクトル不要）
        reader = TagReader(load_vectors=False)
        
        if not reader.is_data_loaded()['tsv']:
            print("タグデータが見つかりませんでした", file=sys.stderr)
            sys.exit(1)
        
        # タグ出現数と共起数を取得
        tag_counter, cooc_counter = load_tag_data_from_reader(reader)
        
        if not tag_counter:
            print("タグデータが見つかりませんでした", file=sys.stderr)
            sys.exit(1)
        
        # 通常の共起率分析を実行
        display_tag_cooc_rates(reader, tag_counter, cooc_counter)
        
        # 上位100タグの共起率統計とヒストグラムを表示
        cooc_rates_with_tags = collect_cooc_rates_with_tags(tag_counter, cooc_counter, top_n=100)
        cooc_rates = collect_cooc_rates(tag_counter, cooc_counter, top_n=100)
        
        display_top_cooc_rates(cooc_rates_with_tags, top_n=20)
        display_cooc_rate_statistics(cooc_rates, top_n=100)
        display_cooc_rate_histogram(cooc_rates, top_n=100)
        
    except Exception as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
