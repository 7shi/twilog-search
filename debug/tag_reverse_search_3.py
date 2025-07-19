#!/usr/bin/env python3
"""
タグベース逆引き検索のmean手法特化検証（TagReader最適化版）
- TagReaderの新メソッドcalculate_all_tag_similaritiessを使用
- 全タグとの類似度計算でtop_k制限を排除
- mean手法のみに絞った効率的な検証
固定シードによる10サンプル検証で統計的分析を実行
"""
import asyncio
import random
import sys
import numpy as np
from pathlib import Path
from typing import Dict, List

# プロジェクトのsrcディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from batch_reader import BatchReader
from tag_reader import TagReader
from embed_client import EmbedClient


class ReverseSearchValidator:
    """逆引き検索検証クラス（mean手法特化版）"""
    
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
    
    async def get_tag_similarities(self, summary: str) -> Dict[str, float]:
        """summaryから全タグとの類似度を計算（TagReader最適化版）"""
        # summaryをベクトル化
        result = await self.embed_client.embed_text("トピック: " + summary)
        summary_vector = self.embed_client.decode_vector(result)
        
        # ベクトルの形状を調整
        if summary_vector.dim() == 2 and summary_vector.shape[0] == 1:
            summary_vector = summary_vector.squeeze(0)
        
        # TagReaderの新メソッドを使用（全タグとの類似度を効率的に計算）
        similarities = self.tag_reader.calculate_all_tag_similarities(summary_vector)
        
        return similarities
    
    def get_all_posts_tags(self) -> Dict[str, List[str]]:
        """全投稿のタグ情報を取得"""
        all_posts_tags = {}
        for post_id, data in self.batch_reader.summaries_data.items():
            all_posts_tags[post_id] = data['tags']
        return all_posts_tags
    
    def calculate_post_scores(self, similarities: Dict[str, float], all_posts_tags: Dict[str, List[str]]) -> Dict[str, float]:
        """全投稿をmean手法でスコアリング"""
        results = {}
        
        for post_id, tags in all_posts_tags.items():
            results[post_id] = sum(similarities[tag] for tag in tags) / len(tags) if tags else 0.0
        
        return results
    
    def get_ranking(self, post_scores: Dict[str, float], target_post_id: str) -> int:
        """mean手法での元投稿ランキングを計算"""
        # mean手法でソート（降順）
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
    
    async def validate_single_sample(self, post_id: str) -> int:
        """単一サンプルの逆引き検証"""
        # サンプル情報取得
        sample_data = self.batch_reader.summaries_data[post_id]
        summary = sample_data['summary']
        tags = sample_data['tags']
        
        print(f"\n--- 検証中: {post_id} ---")
        print(f"Summary: {summary}")
        print(f"Tags: {tags}")
        
        # タグ類似度計算（TagReader最適化版）
        similarities = await self.get_tag_similarities(summary)
        
        # 全投稿スコアリング
        all_posts_tags = self.get_all_posts_tags()
        post_scores = self.calculate_post_scores(similarities, all_posts_tags)
        
        # ランキング計算
        ranking = self.get_ranking(post_scores, post_id)
        
        print(f"mean手法での順位: {ranking}位")
        
        return ranking
    
    async def run_validation(self, seed: int = 42, sample_size: int = 10):
        """固定シード検証の実行"""
        print("=== タグベース逆引き検索 mean手法特化検証（TagReader最適化版） ===\n")
        
        # 初期化
        await self.initialize()
        
        # サンプル抽出
        samples = self.extract_fixed_samples(seed, sample_size)
        
        # 各サンプルで検証
        all_rankings = {}
        for i, post_id in enumerate(samples, 1):
            print(f"\n[{i}/{sample_size}] 検証実行中...")
            ranking = await self.validate_single_sample(post_id)
            all_rankings[post_id] = ranking
        
        # 統計分析
        self.analyze_results(all_rankings)
    
    def analyze_results(self, all_rankings: Dict[str, int]):
        """統計分析と結果出力"""
        print(f"\n=== {len(all_rankings)}サンプル固定シード検証結果（mean手法特化版） ===\n")
        
        # サンプル別順位表示
        print("サンプル別順位（mean手法での元投稿ランキング）:")
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
        
        print(f"\nmean手法統計:")
        print(f"  平均順位: {avg_rank:.1f}")
        print(f"  中央値順位: {median_rank:.1f}")
        print(f"  Top10率: {top10_rate:.0f}%")
        print(f"  Top20率: {top20_rate:.0f}%")
        print(f"  Top100率: {top100_rate:.0f}%")


async def main():
    """メイン処理"""
    validator = ReverseSearchValidator()
    await validator.run_validation(seed=42, sample_size=10)


if __name__ == "__main__":
    asyncio.run(main())
