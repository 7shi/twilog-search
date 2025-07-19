#!/usr/bin/env python3
"""
コアタグ特定アルゴリズムの検証ツール
- 固定シード（42）による100件サンプリング
- summaryから全タグとの類似度計算
- トップK（K=10,20）に元々のtagsが何件含まれるかを集計
- 統計分析（適中率、平均ヒット数等）を出力
"""
import asyncio
import random
import sys
import numpy as np
from pathlib import Path
from typing import Dict, List, Set, Tuple
from collections import Counter

# プロジェクトのsrcディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from batch_reader import BatchReader
from tag_reader import TagReader
from embed_client import EmbedClient


class CoreTagValidator:
    """コアタグ特定アルゴリズムの検証クラス"""
    
    def __init__(self):
        self.batch_reader = None
        self.tag_reader = None
        self.embed_client = None
    
    async def initialize(self):
        """各コンポーネントを初期化"""
        # BatchReaderを初期化
        batch_dir = Path('batch')
        results_jsonl = batch_dir / 'results.jsonl'
        
        self.batch_reader = BatchReader(results_jsonl)
        self.batch_reader.initialize()
        
        # TagReaderを初期化
        self.tag_reader = TagReader()
        
        # EmbedClientを初期化
        self.embed_client = EmbedClient()
        
        print("初期化完了:")
        print(f"  バッチデータ件数: {len(self.batch_reader.summaries_data)}")
        print(f"  ユニークタグ数: {self.tag_reader.get_tag_count()}")
        print(f"  ベクトル次元数: {self.tag_reader.get_vector_dimension()}")
    
    def extract_fixed_samples(self, seed: int = 42, sample_size: int = 100) -> List[str]:
        """固定シードで再現可能なサンプル抽出（タグありのみ）"""
        random.seed(seed)
        np.random.seed(seed)
        
        # タグが存在する投稿のみをフィルタリング
        tagged_posts = []
        for post_id, data in self.batch_reader.summaries_data.items():
            if data['tags']:  # タグが空でない場合のみ
                tagged_posts.append(post_id)
        
        print(f"タグ付き投稿: {len(tagged_posts)}件 / 全投稿: {len(self.batch_reader.summaries_data)}件")
        
        # タグ付き投稿からサンプリング
        samples = random.sample(tagged_posts, sample_size)
        
        print(f"固定シード({seed})で{sample_size}サンプル抽出完了（タグありのみ）")
        return samples
    
    
    def calculate_hit_metrics(self, original_tags: List[str], top_tags: List[str]) -> Dict[str, int]:
        """元のタグとトップKタグのヒット数を計算"""
        original_set = set(original_tags)
        top_set = set(top_tags)
        
        hits = len(original_set & top_set)
        total_original = len(original_set)
        
        return {
            'hits': hits,
            'total_original': total_original,
            'top_k_size': len(top_tags)
        }
    
    async def validate_single_sample(self, post_id: str, k_values: List[int]) -> Dict[str, Dict]:
        """単一サンプルの検証"""
        # サンプル情報取得
        sample_data = self.batch_reader.summaries_data[post_id]
        summary = sample_data['summary']
        original_tags = sample_data['tags']
        
        print(f"\n--- 検証中: {post_id} ---")
        print(f"Summary: {summary}")
        print(f"Original Tags ({len(original_tags)}): {original_tags}")
        
        # summaryをベクトル化（一度だけ実行）
        result = await self.embed_client.embed_text("トピック: " + summary)
        summary_vector = self.embed_client.decode_vector(result)
        
        # ベクトルの形状を調整
        if summary_vector.dim() == 2 and summary_vector.shape[0] == 1:
            summary_vector = summary_vector.squeeze(0)
        
        # TagReaderで全タグとの類似度計算（一度だけ実行）
        similarities = self.tag_reader.calculate_all_tag_similarities(summary_vector)
        
        # 類似度順でソート（一度だけ実行）
        sorted_tags = sorted(similarities.items(), key=lambda x: x[1], reverse=True)
        
        results = {}
        
        # 各K値で検証（ソート済みのリストから切り出すだけ）
        for k in k_values:
            top_tags = [tag for tag, _ in sorted_tags[:k]]
            metrics = self.calculate_hit_metrics(original_tags, top_tags)
            
            results[f'k_{k}'] = {
                'top_tags': top_tags,
                'metrics': metrics
            }
            
            print(f"Top-{k} Tags: {top_tags[:5]}{'...' if len(top_tags) > 5 else ''}")
            print(f"  ヒット数: {metrics['hits']}/{metrics['total_original']} タグ")
        
        return results
    
    async def run_validation(self, seed: int = 42, sample_size: int = 100, k_values: List[int] = [10, 20]):
        """固定シード検証の実行"""
        print("=== コアタグ特定アルゴリズム検証 ===\n")
        
        # 初期化
        await self.initialize()
        
        # サンプル抽出
        samples = self.extract_fixed_samples(seed, sample_size)
        
        # 各サンプルで検証
        all_results = {}
        for i, post_id in enumerate(samples, 1):
            print(f"\n[{i}/{sample_size}] 検証実行中...")
            results = await self.validate_single_sample(post_id, k_values)
            all_results[post_id] = results
        
        # 統計分析
        self.analyze_results(all_results, k_values, sample_size)
    
    def analyze_results(self, all_results: Dict[str, Dict], k_values: List[int], sample_size: int):
        """統計分析と結果出力"""
        print(f"\n=== {sample_size}サンプル固定シード検証結果 ===\n")
        
        for k in k_values:
            print(f"--- Top-{k} 統計 ---")
            
            # メトリクス収集
            all_hits = []
            all_hit_rates = []
            all_original_counts = []
            perfect_matches = 0
            
            for post_id, results in all_results.items():
                metrics = results[f'k_{k}']['metrics']
                hits = metrics['hits']
                total_original = metrics['total_original']
                
                all_hits.append(hits)
                all_original_counts.append(total_original)
                
                # 適中率計算（元タグ数が0の場合は除外）
                if total_original > 0:
                    hit_rate = hits / total_original
                    all_hit_rates.append(hit_rate)
                    
                    # 完全一致（元タグ全てがトップKに含まれる）
                    if hits == total_original:
                        perfect_matches += 1
            
            # 統計計算
            avg_hits = np.mean(all_hits)
            avg_hit_rate = np.mean(all_hit_rates) if all_hit_rates else 0
            avg_original_count = np.mean(all_original_counts)
            perfect_match_rate = perfect_matches / len(all_results) * 100
            
            # ヒット数分布
            hit_counter = Counter(all_hits)
            
            print(f"  平均ヒット数: {avg_hits:.2f}")
            print(f"  平均適中率: {avg_hit_rate:.1%}")
            print(f"  平均元タグ数: {avg_original_count:.1f}")
            print(f"  完全一致率: {perfect_match_rate:.1f}% ({perfect_matches}/{len(all_results)})")
            
            print(f"  ヒット数分布:")
            for hits in sorted(hit_counter.keys()):
                count = hit_counter[hits]
                percentage = count / len(all_results) * 100
                print(f"    {hits}ヒット: {count}件 ({percentage:.1f}%)")
            
            print()
        
        # K値間比較
        if len(k_values) > 1:
            print("--- K値間比較 ---")
            for k in k_values:
                avg_hits = np.mean([results[f'k_{k}']['metrics']['hits'] for results in all_results.values()])
                avg_hit_rate = np.mean([
                    results[f'k_{k}']['metrics']['hits'] / results[f'k_{k}']['metrics']['total_original']
                    for results in all_results.values()
                    if results[f'k_{k}']['metrics']['total_original'] > 0
                ])
                print(f"  K={k}: 平均ヒット数 {avg_hits:.2f}, 平均適中率 {avg_hit_rate:.1%}")


async def main():
    """メイン処理"""
    validator = CoreTagValidator()
    await validator.run_validation(seed=42, sample_size=100, k_values=[10, 20])


if __name__ == "__main__":
    asyncio.run(main())