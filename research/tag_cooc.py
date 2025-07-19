#!/usr/bin/env python3

from collections import Counter, defaultdict
from pathlib import Path
import sys
import unicodedata
from itertools import combinations

# プロジェクトのsrcディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

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

def load_cooccurrence_data_from_reader(reader: TagReader) -> Counter:
    """TagReaderからタグの共起データを読み込み、共起回数をカウントする"""
    cooc_counter = Counter()
    
    # 各投稿のタグから共起ペアを生成
    for entry in reader.tag_data:
        tags = entry['tags']
        if len(tags) >= 2:
            # 同一投稿内のタグペアの組み合わせを生成
            for tag_pair in combinations(sorted(tags), 2):
                cooc_counter[tag_pair] += 1
    
    return cooc_counter

def display_top_cooccurrences(cooc_counter: Counter, top_n: int = 20):
    """最頻出N個のタグペアの共起を表示"""
    print(f"最頻出{top_n}タグペア共起:")
    print("-" * 70)
    
    for i, (tag_pair, count) in enumerate(cooc_counter.most_common(top_n), 1):
        tag1, tag2 = tag_pair
        tag1_formatted = format_with_width(tag1, 15)
        tag2_formatted = format_with_width(tag2, 15)
        print(f"{i:2d}. {tag1_formatted} × {tag2_formatted} {count:>6,}回")

def display_cooccurrence_statistics(cooc_counter: Counter):
    """共起統計情報を表示"""
    total_pairs = len(cooc_counter)
    total_cooccurrences = sum(cooc_counter.values())
    max_cooccurrence = max(cooc_counter.values()) if cooc_counter else 0
    
    print(f"\n共起統計情報:")
    print("-" * 40)
    print(f"総タグペア数（ユニーク）: {total_pairs:,}")
    print(f"総共起回数: {total_cooccurrences:,}")
    print(f"最大共起回数: {max_cooccurrence:,}")
    
    # 順位別共起回数を表示
    print(f"\n順位別共起回数:")
    print("-" * 40)
    most_common = cooc_counter.most_common()
    positions = [10, 20, 50, 100]
    
    for pos in positions:
        if pos <= len(most_common):
            tag_pair, count = most_common[pos - 1]  # 0-indexedなので-1
            tag1, tag2 = tag_pair
            print(f"{pos:3d}位: {count:>6,}回 ({tag1} × {tag2})")
        else:
            print(f"{pos:3d}位: データなし")

def analyze_tag_relationships(cooc_counter: Counter, target_tag: str = None):
    """特定のタグとの共起関係を分析"""
    if target_tag:
        print(f"\n「{target_tag}」との共起関係:")
        print("-" * 50)
        
        related_tags = []
        for (tag1, tag2), count in cooc_counter.items():
            if tag1 == target_tag:
                related_tags.append((tag2, count))
            elif tag2 == target_tag:
                related_tags.append((tag1, count))
        
        if related_tags:
            related_tags.sort(key=lambda x: x[1], reverse=True)
            for i, (related_tag, count) in enumerate(related_tags[:10], 1):
                formatted_tag = format_with_width(related_tag, 20)
                print(f"{i:2d}. {formatted_tag} {count:>6,}回")
        else:
            print(f"「{target_tag}」との共起データが見つかりません")

def display_tags_by_cooccurrence_count(cooc_counter: Counter, top_n: int = 20):
    """各タグの共起タグ数で降順ソートして表示"""
    print(f"\n共起タグ数上位{top_n}タグ:")
    print("-" * 50)
    
    # 各タグの共起タグ数をカウント
    tag_cooc_counts = defaultdict(set)
    for (tag1, tag2), count in cooc_counter.items():
        tag_cooc_counts[tag1].add(tag2)
        tag_cooc_counts[tag2].add(tag1)
    
    # 共起タグ数でソート
    sorted_tags = sorted(tag_cooc_counts.items(), key=lambda x: len(x[1]), reverse=True)
    
    for i, (tag, cooc_tags) in enumerate(sorted_tags[:top_n], 1):
        cooc_count = len(cooc_tags)
        formatted_tag = format_with_width(tag, 20)
        print(f"{i:2d}. {formatted_tag} {cooc_count:>6,}個")

def display_tags_with_percentages(cooc_counter: Counter, top_n: int = 30):
    """各タグの共起タグ数と上位関連タグの比率を表示"""
    print(f"\n共起タグ数上位{top_n}タグ（関連タグ比率付き）:")
    print("-" * 100)
    
    # 各タグの共起データを収集
    tag_cooc_data = defaultdict(list)
    for (tag1, tag2), count in cooc_counter.items():
        tag_cooc_data[tag1].append((tag2, count))
        tag_cooc_data[tag2].append((tag1, count))
    
    # 各タグの共起タグ数でソート
    tag_cooc_counts = {tag: len(cooc_list) for tag, cooc_list in tag_cooc_data.items()}
    sorted_tags = sorted(tag_cooc_counts.items(), key=lambda x: x[1], reverse=True)
    
    # 上位30タグの最大表示幅を計算
    max_width = 0
    for i, (tag, cooc_count) in enumerate(sorted_tags[:top_n], 1):
        width = get_display_width(tag)
        max_width = max(max_width, width)
    
    for i, (tag, cooc_count) in enumerate(sorted_tags[:top_n], 1):
        # 関連タグを共起回数でソート
        related_tags = sorted(tag_cooc_data[tag], key=lambda x: x[1], reverse=True)
        
        # 総共起回数を計算
        total_cooc_count = sum(count for _, count in related_tags)
        
        # 上位12個の関連タグとその比率を取得
        top_related = []
        for related_tag, count in related_tags[:12]:
            percentage = (count / total_cooc_count) * 100
            top_related.append(f"{related_tag}({percentage:.1f}%)")
        
        # 最初の行の構成要素
        formatted_tag = format_with_width(tag, max_width)
        first_line = f"{i:2d}. {formatted_tag} {cooc_count:>6,}個"
        
        # 2行目以降の開始位置を計算（番号 + ". " + タグ名 + " " + 個数 + "個 " の幅 + 1スペース）
        indent = len(f"{i:2d}. ") + max_width + len(f" {cooc_count:>6,}個 ")
        indent_str = " " * (indent + 1)
        
        # 4個ずつ3行に分けて表示
        if len(top_related) > 0:
            # 1行目：基本情報 + 関連タグ1-4
            line1_tags = " ".join(top_related[:4])
            print(f"{first_line} {line1_tags}")
            
            # 2行目：関連タグ5-8
            if len(top_related) > 4:
                line2_tags = " ".join(top_related[4:8])
                print(f"{indent_str}{line2_tags}")
            
            # 3行目：関連タグ9-12
            if len(top_related) > 8:
                line3_tags = " ".join(top_related[8:12])
                print(f"{indent_str}{line3_tags}")
        else:
            print(first_line)

def main():
    try:
        # TagReaderを使用してデータを読み込み（ベクトル不要）
        reader = TagReader(load_vectors=False)
        
        if not reader.is_data_loaded()['tsv']:
            print("タグデータが見つかりませんでした", file=sys.stderr)
            sys.exit(1)
        
        cooc_counter = load_cooccurrence_data_from_reader(reader)
        
        if not cooc_counter:
            print("共起データが見つかりませんでした", file=sys.stderr)
            sys.exit(1)
        
        display_top_cooccurrences(cooc_counter)
        display_cooccurrence_statistics(cooc_counter)
        display_tags_with_percentages(cooc_counter)
        
        # 最頻出タグとの関係を分析
        analyze_tag_relationships(cooc_counter, "数学")
        analyze_tag_relationships(cooc_counter, "AI")
        
    except Exception as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()