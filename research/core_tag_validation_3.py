#!/usr/bin/env python3
"""
コアタグベース検索アルゴリズムの検証ツール
- 固定シード（42）による10件サンプリング
- summaryから0.89閾値でコアタグを特定
- 各コアタグについてポストタグとの最大類似度を計算
- mean(max, max, ...)方式でのスコアリング検証
"""
import asyncio
import random
import sys
import numpy as np
from pathlib import Path
from typing import Dict, List
import torch

# プロジェクトのsrcディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from batch_reader import BatchReader
from tag_reader import TagReader
from embed_client import EmbedClient


class CoreTagSearchValidator:
    """コアタグベース検索検証クラス"""
    
    def __init__(self):
        self.batch_reader = None
        self.tag_reader = None
        self.embed_client = None
        self.core_top_k = 5  # 固定コアタグ数
    
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
        print(f"  コアタグ数: top_{self.core_top_k}")
    
    def extract_fixed_samples(self, seed: int = 42, sample_size: int = 10) -> List[str]:
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
    
    async def get_core_tags(self, summary: str) -> List[str]:
        """summaryからtop_k個のコアタグを特定"""
        # summaryをベクトル化
        result = await self.embed_client.embed_text("トピック: " + summary)
        summary_vector = self.embed_client.decode_vector(result)
        
        # ベクトルの形状を調整
        if summary_vector.dim() == 2 and summary_vector.shape[0] == 1:
            summary_vector = summary_vector.squeeze(0)
        
        # TagReaderで全タグとの類似度計算
        similarities = self.tag_reader.calculate_all_tag_similarities(summary_vector)
        
        # 類似度順でソートしてtop_k個を取得
        sorted_tags = sorted(similarities.items(), key=lambda x: x[1], reverse=True)
        core_tags = [tag for tag, _ in sorted_tags[:self.core_top_k]]
        
        return core_tags
    
    def get_core_tag_similarities(self, core_tags: List[str]) -> Dict[str, Dict[str, float]]:
        """コアタグと全タグとの類似度マトリックスを計算"""
        core_similarities = {}
        for core_tag in core_tags:
            if core_tag in self.tag_reader.tag_to_index:
                # コアタグのベクトルを取得
                core_idx = self.tag_reader.tag_to_index[core_tag]
                core_vector = self.tag_reader.tag_vectors[core_idx:core_idx+1]  # shape: [1, 768]
                
                # 全タグとの類似度計算
                all_similarities = self.tag_reader.calculate_all_tag_similarities(core_vector.squeeze(0))
                core_similarities[core_tag] = all_similarities
            else:
                # コアタグが見つからない場合（通常発生しないはず）
                core_similarities[core_tag] = {}
        
        return core_similarities
    
    def calculate_post_score(self, core_similarities: Dict[str, Dict[str, float]], post_tags: List[str]) -> float:
        """mean(max, max, ...)方式でポストスコアを計算"""
        if not core_similarities or not post_tags:
            return 0.0
        
        core_scores = []
        for core_tag, similarities in core_similarities.items():
            # このコアタグについて、ポストタグとの最大類似度を取得
            post_similarities = [similarities.get(tag, 0.0) for tag in post_tags]
            max_similarity = max(post_similarities) if post_similarities else 0.0
            core_scores.append(max_similarity)
        
        # 平均を取る: mean(max, max, ...)
        return np.mean(core_scores) if core_scores else 0.0
    
    def get_all_posts_tags(self) -> Dict[str, List[str]]:
        """全投稿のタグ情報を取得"""
        all_posts_tags = {}
        for post_id, data in self.batch_reader.summaries_data.items():
            all_posts_tags[post_id] = data['tags']
        return all_posts_tags
    
    def get_ranking(self, core_similarities: Dict[str, Dict[str, float]], target_post_id: str) -> int:
        """コアタグベース検索での元投稿ランキングを計算"""
        all_posts_tags = self.get_all_posts_tags()
        
        # 全投稿をスコアリング
        post_scores = {}
        for post_id, post_tags in all_posts_tags.items():
            post_scores[post_id] = self.calculate_post_score(core_similarities, post_tags)
        
        # スコア順でソート（降順）
        sorted_posts = sorted(
            post_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        # 元投稿の順位を検索
        for rank, (post_id, _) in enumerate(sorted_posts, 1):
            if post_id == target_post_id:
                return rank
        
        return len(sorted_posts) + 1  # 見つからない場合は最下位+1
    
    async def validate_single_sample(self, post_id: str, sample_num: int) -> int:
        """単一サンプルの検証"""
        # サンプル情報取得
        sample_data = self.batch_reader.summaries_data[post_id]
        summary = sample_data['summary']
        original_tags = sample_data['tags']
        
        print(f"\n[{sample_num}] --- 検証中: {post_id} ---")
        print(f"Summary: {summary}")
        print(f"Original Tags ({len(original_tags)}): {original_tags}")
        
        # コアタグ特定
        core_tags = await self.get_core_tags(summary)
        print(f"Core Tags ({len(core_tags)}): {core_tags}")
        
        # コアタグと全タグとの類似度マトリックス計算
        core_similarities = self.get_core_tag_similarities(core_tags)
        
        # ランキング計算
        ranking = self.get_ranking(core_similarities, post_id)
        
        print(f"コアタグベース検索での順位: {ranking}位")
        
        return ranking
    
    async def run_validation(self, seed: int = 42, sample_size: int = 10):
        """固定シード検証の実行"""
        print("=== コアタグベース検索アルゴリズム検証 ===\n")
        
        # 初期化
        await self.initialize()
        
        # サンプル抽出
        samples = self.extract_fixed_samples(seed, sample_size)
        
        # 各サンプルで検証
        all_rankings = {}
        for i, post_id in enumerate(samples, 1):
            ranking = await self.validate_single_sample(post_id, i)
            all_rankings[post_id] = ranking
        
        # 統計分析
        self.analyze_results(all_rankings)
    
    def analyze_results(self, all_rankings: Dict[str, int]):
        """統計分析と結果出力"""
        print(f"\n=== {len(all_rankings)}サンプル コアタグベース検索検証結果 ===\n")
        
        # サンプル別順位表示
        print("サンプル別順位（コアタグベース検索での元投稿ランキング）:")
        print(f"{'ID':<20s} {'順位':<10s}")
        print("-" * 30)
        
        for post_id, ranking in all_rankings.items():
            print(f"{str(post_id):<20s} {ranking:<10d}")
        
        # 統計計算
        ranks = list(all_rankings.values())
        avg_rank = np.mean(ranks)
        median_rank = np.median(ranks)
        top10_rate = sum(1 for r in ranks if r <= 10) / len(ranks) * 100
        top20_rate = sum(1 for r in ranks if r <= 20) / len(ranks) * 100
        top100_rate = sum(1 for r in ranks if r <= 100) / len(ranks) * 100
        
        print(f"\nコアタグベース検索統計:")
        print(f"  平均順位: {avg_rank:.1f}")
        print(f"  中央値順位: {median_rank:.1f}")
        print(f"  Top10率: {top10_rate:.0f}%")
        print(f"  Top20率: {top20_rate:.0f}%")
        print(f"  Top100率: {top100_rate:.0f}%")


async def main():
    """メイン処理"""
    validator = CoreTagSearchValidator()
    await validator.run_validation(seed=42, sample_size=10)


if __name__ == "__main__":
    asyncio.run(main())