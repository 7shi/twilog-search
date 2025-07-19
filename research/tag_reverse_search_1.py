#!/usr/bin/env python3
"""
タグベース逆引き検索の6手法比較検証
固定シードによる10サンプル検証で統計的分析を実行
"""
import asyncio
import random
import sys
import unicodedata
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict

# プロジェクトのsrcディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from batch_reader import BatchReader
from tag_reader import TagReader
from embed_client import EmbedClient


def get_display_width(text: str) -> int:
    """文字列の表示幅を取得（全角文字は2、半角文字は1として計算）"""
    return sum(2 if unicodedata.east_asian_width(c) in ('F', 'W') else 1 for c in text)


def format_with_width(text: str, width: int, align: str = 'left') -> str:
    """表示幅を考慮した文字列整形"""
    current_width = get_display_width(text)
    padding = max(0, width - current_width)
    
    if align == 'right':
        return ' ' * padding + text
    else:  # left
        return text + ' ' * padding


class TagScorer:
    """6つのスコアリング手法を実装するクラス"""
    
    @staticmethod
    def mean_score(scores: List[float]) -> float:
        """平均値スコア"""
        return np.mean(scores) if scores else 0.0
    
    @staticmethod
    def median_score(scores: List[float]) -> float:
        """中央値スコア"""
        return np.median(scores) if scores else 0.0
    
    @staticmethod
    def max_score(scores: List[float]) -> float:
        """最大値スコア"""
        return np.max(scores) if scores else 0.0
    
    @staticmethod
    def q75_score(scores: List[float]) -> float:
        """75パーセンタイルスコア"""
        return np.percentile(scores, 75) if scores else 0.0
    
    @staticmethod
    def top_k_score(scores: List[float], k: int = 3) -> float:
        """トップK平均スコア"""
        if not scores:
            return 0.0
        sorted_scores = sorted(scores, reverse=True)
        top_k = min(k, len(sorted_scores))
        return np.mean(sorted_scores[:top_k])
    
    @staticmethod
    def weighted_score(scores: List[float]) -> float:
        """重み付き平均スコア（順位重み: 1, 1/2, 1/3, ...）"""
        if not scores:
            return 0.0
        sorted_scores = sorted(scores, reverse=True)
        weights = [1.0 / (i + 1) for i in range(len(sorted_scores))]
        return np.average(sorted_scores, weights=weights)
    
    @classmethod
    def calculate_all_scores(cls, scores: List[float]) -> Dict[str, float]:
        """全手法でスコアを計算"""
        return {
            'mean': cls.mean_score(scores),
            'median': cls.median_score(scores),
            'max': cls.max_score(scores),
            'q75': cls.q75_score(scores),
            'top_k': cls.top_k_score(scores),
            'weighted': cls.weighted_score(scores)
        }


class ReverseSearchValidator:
    """逆引き検索検証クラス"""
    
    def __init__(self):
        self.batch_reader = None
        self.tag_reader = None
        self.embed_client = None
        self.scorer = TagScorer()
    
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
        """summaryから全タグとの類似度を計算"""
        # summaryをベクトル化
        result = await self.embed_client.embed_text("トピック: " + summary)
        summary_vector = self.embed_client.decode_vector(result)
        
        # ベクトルの形状を調整
        if summary_vector.dim() == 2 and summary_vector.shape[0] == 1:
            summary_vector = summary_vector.squeeze(0)
        
        # 上位類似タグのみ計算（処理時間短縮）
        similar_tags = self.tag_reader.search_similar_tags(summary_vector, top_k=1000)
        
        # 辞書に変換
        similarities = {tag: float(score) for tag, score in similar_tags}
        return similarities
    
    def get_all_posts_tags(self) -> Dict[str, List[str]]:
        """全投稿のタグ情報を取得"""
        all_posts_tags = {}
        for post_id, data in self.batch_reader.summaries_data.items():
            all_posts_tags[post_id] = data['tags']
        return all_posts_tags
    
    def calculate_post_scores(self, similarities: Dict[str, float], all_posts_tags: Dict[str, List[str]]) -> Dict[str, Dict[str, float]]:
        """全投稿を6手法でスコアリング"""
        results = {}
        
        for post_id, tags in all_posts_tags.items():
            # タグを類似度スコアに変換
            tag_scores = [similarities.get(tag, 0.0) for tag in tags]
            
            # 6手法でスコアリング
            results[post_id] = self.scorer.calculate_all_scores(tag_scores)
        
        return results
    
    def get_rankings(self, post_scores: Dict[str, Dict[str, float]], target_post_id: str) -> Dict[str, int]:
        """各手法での元投稿ランキングを計算"""
        rankings = {}
        methods = ['mean', 'median', 'max', 'q75', 'top_k', 'weighted']
        
        for method in methods:
            # 該当手法でソート（降順）
            sorted_posts = sorted(
                post_scores.items(),
                key=lambda x: x[1][method],
                reverse=True
            )
            
            # 元投稿の順位を検索
            for rank, (post_id, _) in enumerate(sorted_posts, 1):
                if post_id == target_post_id:
                    rankings[method] = rank
                    break
            else:
                rankings[method] = len(sorted_posts) + 1  # 見つからない場合は最下位+1
        
        return rankings
    
    async def validate_single_sample(self, post_id: str) -> Dict[str, int]:
        """単一サンプルの逆引き検証"""
        # サンプル情報取得
        sample_data = self.batch_reader.summaries_data[post_id]
        summary = sample_data['summary']
        tags = sample_data['tags']
        
        print(f"\n--- 検証中: {post_id} ---")
        print(f"Summary: {summary}")
        print(f"Tags: {tags}")
        
        # タグ類似度計算
        similarities = await self.get_tag_similarities(summary)
        
        # 全投稿スコアリング
        all_posts_tags = self.get_all_posts_tags()
        post_scores = self.calculate_post_scores(similarities, all_posts_tags)
        
        # ランキング計算
        rankings = self.get_rankings(post_scores, post_id)
        
        print("各手法での順位:")
        for method, rank in rankings.items():
            print(f"  {method:8s}: {rank:6d}位")
        
        return rankings
    
    async def run_validation(self, seed: int = 42, sample_size: int = 10):
        """固定シード検証の実行"""
        print("=== タグベース逆引き検索 6手法比較検証 ===\n")
        
        # 初期化
        await self.initialize()
        
        # サンプル抽出
        samples = self.extract_fixed_samples(seed, sample_size)
        
        # 各サンプルで検証
        all_rankings = {}
        for i, post_id in enumerate(samples, 1):
            print(f"\n[{i}/{sample_size}] 検証実行中...")
            rankings = await self.validate_single_sample(post_id)
            all_rankings[post_id] = rankings
        
        # 統計分析
        self.analyze_results(all_rankings)
    
    def analyze_results(self, all_rankings: Dict[str, Dict[str, int]]):
        """統計分析と結果出力"""
        methods = ['mean', 'median', 'max', 'q75', 'top_k', 'weighted']
        
        print(f"\n=== {len(all_rankings)}サンプル固定シード検証結果 ===\n")
        
        # サンプル別順位表示
        print("サンプル別順位（各手法での元投稿ランキング）:")
        header = "ID" + " " * 18 + " ".join(f"{method:>8s}" for method in methods)
        print(header)
        print("-" * len(header))
        
        for post_id, rankings in all_rankings.items():
            id_str = str(post_id)
            rank_strs = [f"{rankings[method]:8d}" for method in methods]
            print(f"{id_str:<20s} {' '.join(rank_strs)}")
        
        # 手法別統計
        print(f"\n手法別統計:")
        print(f"{'手法':<10s} {'平均順位':<8s} {'中央値順位':<10s} {'Top10率':<8s} {'Top20率':<8s} {'Top100率':<8s}")
        print("-" * 60)
        
        best_method = None
        best_avg_rank = float('inf')
        
        for method in methods:
            ranks = [all_rankings[post_id][method] for post_id in all_rankings.keys()]
            
            avg_rank = np.mean(ranks)
            median_rank = np.median(ranks)
            top10_rate = sum(1 for r in ranks if r <= 10) / len(ranks) * 100
            top20_rate = sum(1 for r in ranks if r <= 20) / len(ranks) * 100
            top100_rate = sum(1 for r in ranks if r <= 100) / len(ranks) * 100
            
            marker = "★" if avg_rank < best_avg_rank else " "
            if avg_rank < best_avg_rank:
                best_avg_rank = avg_rank
                best_method = method
            
            print(f"{method:<10s} {avg_rank:>7.1f}  {median_rank:>9.1f}  {top10_rate:>7.0f}%  {top20_rate:>7.0f}%  {top100_rate:>7.0f}% {marker}")
        
        print(f"\n最優秀手法: {best_method} (平均順位: {best_avg_rank:.1f})")


async def main():
    """メイン処理"""
    validator = ReverseSearchValidator()
    await validator.run_validation(seed=42, sample_size=10)


if __name__ == "__main__":
    asyncio.run(main())