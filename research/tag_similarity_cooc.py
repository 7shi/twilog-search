#!/usr/bin/env python3

from collections import Counter, defaultdict
from pathlib import Path
import sys
import unicodedata

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

def get_cooccurrence_rate(tag_a: str, tag_b: str, tag_counter: Counter, cooc_counter: dict) -> float:
    """タグAからタグBへの共起率を計算"""
    if tag_a not in cooc_counter or tag_b not in cooc_counter[tag_a]:
        return 0.0
    
    tag_a_count = tag_counter[tag_a]
    if tag_a_count == 0:
        return 0.0
    
    cooc_count = cooc_counter[tag_a][tag_b]
    return cooc_count / tag_a_count

def get_similarity_score(tag_a: str, tag_b: str, reader: TagReader) -> float:
    """タグAとタグBの類似度スコアを取得"""
    vector_a = reader.get_tag_vector(tag_a)
    vector_b = reader.get_tag_vector(tag_b)
    
    if vector_a is None or vector_b is None:
        return 0.0
    
    # コサイン類似度を計算
    import numpy as np
    dot_product = np.dot(vector_a, vector_b)
    norm_a = np.linalg.norm(vector_a)
    norm_b = np.linalg.norm(vector_b)
    
    if norm_a == 0 or norm_b == 0:
        return 0.0
    
    return dot_product / (norm_a * norm_b)

def find_similarity_cooccurrence_inversions(reader: TagReader, tag_counter: Counter, cooc_counter: dict, top_n: int = 30) -> list:
    """類似度<共起率となるタグペアを検出"""
    inversions = []
    
    # 上位タグを取得
    top_tags = [tag for tag, _ in tag_counter.most_common(top_n)]
    
    # 各タグペアについて類似度と共起率を比較
    for i, tag_a in enumerate(top_tags):
        for j, tag_b in enumerate(top_tags):
            if i >= j:  # 重複を避ける（対角線より上のみ）
                continue
            
            # 共起率を計算（双方向）
            cooc_rate_ab = get_cooccurrence_rate(tag_a, tag_b, tag_counter, cooc_counter)
            cooc_rate_ba = get_cooccurrence_rate(tag_b, tag_a, tag_counter, cooc_counter)
            
            # 類似度を計算
            similarity = get_similarity_score(tag_a, tag_b, reader)
            
            # A→B方向で類似度 < 共起率の場合を記録
            if similarity < cooc_rate_ab and cooc_rate_ab > 0.0:
                inversions.append({
                    'tag_a': tag_a,
                    'tag_b': tag_b,
                    'similarity': similarity,
                    'cooccurrence_rate': cooc_rate_ab,
                    'difference': cooc_rate_ab - similarity,
                    'direction': 'A→B',
                    'cooc_rate_ab': cooc_rate_ab,
                    'cooc_rate_ba': cooc_rate_ba,
                    'count_a': tag_counter[tag_a],
                    'count_b': tag_counter[tag_b]
                })
            
            # B→A方向で類似度 < 共起率の場合を記録
            if similarity < cooc_rate_ba and cooc_rate_ba > 0.0:
                inversions.append({
                    'tag_a': tag_b,  # 逆転
                    'tag_b': tag_a,  # 逆転
                    'similarity': similarity,
                    'cooccurrence_rate': cooc_rate_ba,
                    'difference': cooc_rate_ba - similarity,
                    'direction': 'B→A',
                    'cooc_rate_ab': cooc_rate_ba,  # 逆転後の値
                    'cooc_rate_ba': cooc_rate_ab,  # 逆転後の値
                    'count_a': tag_counter[tag_b],  # 逆転
                    'count_b': tag_counter[tag_a]   # 逆転
                })
    
    # 差の大きい順にソート
    inversions.sort(key=lambda x: x['difference'], reverse=True)
    
    return inversions

def display_inversions(inversions: list, top_n: int = 20):
    """類似度<共起率となるタグペアを表示"""
    if not inversions:
        print("類似度<共起率となるタグペアは見つかりませんでした")
        return
    
    print(f"類似度<共起率となるタグペア（上位{min(top_n, len(inversions))}組）:")
    print("=" * 110)
    print(f"{'順位':>2} {'タグA':<15} {'タグB':<15} {'類似度':>6} {'共起率':>6} {'差':>6} {'方向':>5} {'出現A':>6} {'出現B':>6}")
    print("-" * 110)
    
    for i, inversion in enumerate(inversions[:top_n], 1):
        tag_a = inversion['tag_a'][:13] if len(inversion['tag_a']) > 13 else inversion['tag_a']
        tag_b = inversion['tag_b'][:13] if len(inversion['tag_b']) > 13 else inversion['tag_b']
        
        print(f"{i:2d} {tag_a:<15} {tag_b:<15} "
              f"{inversion['similarity']:6.3f} {inversion['cooccurrence_rate']:6.3f} "
              f"{inversion['difference']:6.3f} {inversion['direction']:>5} "
              f"{inversion['count_a']:6,} {inversion['count_b']:6,}")

def display_detailed_analysis(inversions: list, top_n: int = 10):
    """詳細な分析結果を表示"""
    if not inversions:
        return
    
    print(f"\n詳細分析（上位{min(top_n, len(inversions))}組）:")
    print("=" * 80)
    
    for i, inversion in enumerate(inversions[:top_n], 1):
        print(f"\n{i}. {inversion['tag_a']} → {inversion['tag_b']} ({inversion['direction']})")
        print(f"   類似度: {inversion['similarity']:.3f}")
        print(f"   共起率: {inversion['cooccurrence_rate']:.3f}")
        print(f"   差: {inversion['difference']:.3f}")
        print(f"   方向別共起率: A→B: {inversion['cooc_rate_ab']:.3f}, B→A: {inversion['cooc_rate_ba']:.3f}")
        print(f"   出現回数: {inversion['tag_a']}={inversion['count_a']:,}回, "
              f"{inversion['tag_b']}={inversion['count_b']:,}回")

def display_statistics(inversions: list, total_pairs: int):
    """統計情報を表示"""
    print(f"\n統計情報:")
    print("-" * 40)
    print(f"検査したタグペア数: {total_pairs:,}")
    print(f"類似度<共起率のペア数: {len(inversions):,}")
    print(f"逆転率: {len(inversions)/total_pairs*100:.1f}%")
    
    if inversions:
        differences = [inv['difference'] for inv in inversions]
        similarities = [inv['similarity'] for inv in inversions]
        cooc_rates = [inv['cooccurrence_rate'] for inv in inversions]
        
        print(f"\n逆転ペアの統計:")
        print(f"最大差: {max(differences):.3f}")
        print(f"平均差: {sum(differences)/len(differences):.3f}")
        print(f"平均類似度: {sum(similarities)/len(similarities):.3f}")
        print(f"平均共起率: {sum(cooc_rates)/len(cooc_rates):.3f}")

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
        
        # タグ出現数と共起数を取得
        tag_counter, cooc_counter = load_tag_data_from_reader(reader)
        
        if not tag_counter:
            print("タグデータが見つかりませんでした", file=sys.stderr)
            sys.exit(1)
        
        print("出現頻度上位30タグの類似度vs共起率比較分析")
        print("=" * 60)
        
        # 上位30タグについて類似度<共起率となるペアを検出
        inversions = find_similarity_cooccurrence_inversions(reader, tag_counter, cooc_counter, top_n=30)
        
        # 総ペア数を計算（30C2 = 435、双方向なので倍）
        total_pairs = 30 * 29
        
        # 結果を表示
        display_inversions(inversions, top_n=20)
        display_detailed_analysis(inversions, top_n=10)
        display_statistics(inversions, total_pairs)
        
    except Exception as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()